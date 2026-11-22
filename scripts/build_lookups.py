"""Build the two hand-written lookup tables in workspace.vf.

  workspace.vf.service_department_map  (service, link_type, value, strength, note)
  workspace.vf.service_type_fit        (service, facility_type, fit, note)

Edit the dicts below and re-run:
  /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_lookups.py

The script checks every specialty value against workspace.vf.facilities_clean
(non-shifted, distinct facilities per exploded specialty) and refuses to build if a
value appears in fewer than MIN_FACILITIES facilities.

METHOD (service_type_fit), applied in this order, later steps win:
 1. Each facility_type has a default fit (TYPE_SPEC[...]["default"]).
 2. Services listed under that type's "expected" / "plausible" / "unexpected" override it.
    Broad hospitals (multispecialty, medical college, government, general/nursing home)
    default to plausible; single-specialty types default to unexpected with their own
    services expected and closely related ones plausible; diagnostic_imaging_lab expects
    imaging + lab and finds surgery unexpected; unknown is plausible for all;
    not_a_care_facility is unexpected for all.
 3. Global floors for every care-giving type (all except not_a_care_facility, unknown):
    outpatient_opd and laboratory_pathology are at least plausible; xray is at least
    plausible except in XRAY_NOT_FLOOR types; other_clinical is at least plausible.
 4. EXCEPTIONS (service, facility_type) -> fit set explicitly, with a reason.
Every row's note says which step decided it.
"""
import json
import subprocess

from databricks import sql

MIN_FACILITIES = 20

SERVICES = [
    "dialysis", "caesarean_section", "normal_delivery", "high_risk_obstetrics",
    "nicu", "picu", "icu_critical_care", "ventilator_support",
    "cardiac_surgery", "interventional_cardiology", "stroke_care",
    "mri", "ct_scan", "xray", "ultrasound", "mammography", "nuclear_imaging",
    "burn_care", "trauma_emergency", "ambulance",
    "chemotherapy", "radiotherapy", "cancer_surgery",
    "orthopedic_surgery", "joint_replacement", "neurosurgery", "spine_surgery",
    "general_surgery", "gi_endoscopy", "pulmonology_respiratory", "transplant",
    "blood_bank", "laboratory_pathology", "dental", "eye_surgery",
    "physiotherapy_rehab", "mental_health", "outpatient_opd",
    "infertility_ivf", "dermatology", "ent", "ophthalmology_medical",
    "pediatrics", "obstetrics_maternity", "cosmetic_aesthetic",
    "prosthetics_orthotics", "nephrology_renal", "gastroenterology",
    "other_clinical",
]  # same list as scripts/classify_eval.py (49 labels, prompt pa_single_v1)
# 11 labels added with prompt pa_single_v2 (reports/new_service_labels_proposal.md;
# re-tag in scripts/retag_new_labels.py). General / internal medicine stays outpatient_opd.
NEW_SERVICES_V2 = [
    "urology", "diabetes_endocrinology", "health_checkup_vaccination", "cardiac_diagnostics",
    "neurology", "ayush_traditional_medicine", "gynecology", "proctology", "pain_management",
    "vascular_surgery", "cardiology_medical",
]
SERVICES = SERVICES + NEW_SERVICES_V2

FACILITY_TYPES = [
    "multispecialty_hospital", "general_hospital_or_nursing_home",
    "medical_college_teaching_hospital", "government_health_centre",
    "maternity_women_children", "pediatric", "eye", "dental", "ent_hearing_speech",
    "skin_hair_cosmetic", "ivf_fertility", "kidney_urology", "cardiac", "cancer",
    "orthopedic_spine", "neuro", "gastro_liver", "diagnostic_imaging_lab",
    "physiotherapy_rehab", "mental_health_deaddiction", "ayush_alternative",
    "home_care_or_ambulance", "general_clinic_polyclinic", "other_single_specialty",
    "not_a_care_facility", "unknown",
]

# ---------------------------------------------------------------------------
# service_department_map source
# S = strong (the specialty is this service's own department / subspecialty)
# P = supporting (related department; makes the service more likely, proves nothing)
# Department-only values (internalMedicine, familyMedicine, generalMedicine,
# preventiveMedicine, anesthesia) are over-assigned in this data and are never strong.
# ---------------------------------------------------------------------------
DEF_NOTE = {"S": "specialty is this service's own department or subspecialty",
            "P": "related department; raises likelihood, does not prove the service"}
STRENGTH = {"S": "strong", "P": "supporting"}

OBS = ["gynecologyAndObstetrics", "obstetricsAndGynaecology", "obstetricsAndGynecology",
       "obstetricsAndMaternityCare"]
RADIOLOGY = ["radiology", "diagnosticRadiology", "neuroradiology", "interventionalRadiology",
             "cardiothoracicRadiology", "pediatricRadiology"]
NO_MACHINE = "radiology department does not prove this machine exists"

SPEC = {
    "dialysis": [("nephrology", "S", "nephrology department usually runs haemodialysis; still a department, not proof of a unit"),
                 ("pediatricNephrology", "S", None), ("renalTransplantationUrology", "P", None),
                 ("transplantSurgery", "P", "renal transplant programmes need dialysis"), ("urology", "P", None)],
    "caesarean_section": [(v, "S", "obstetrics department; C-section is core obstetric surgery") for v in OBS]
                         + [("maternalFetalMedicineOrPerinatology", "S", None),
                            ("neonatologyPerinatalMedicine", "P", None), ("anesthesia", "P", "needed for C-section; department-only, over-assigned"),
                            ("anesthesiology", "P", None), ("gynecology", "P", "gynecology alone may exclude obstetrics")],
    "normal_delivery": [(v, "S", None) for v in OBS]
                       + [("maternalFetalMedicineOrPerinatology", "S", None), ("maternalAndChildHealth", "P", None),
                          ("gynecology", "P", "gynecology alone may exclude obstetrics"),
                          ("familyPlanningAndComplexContraception", "P", None)],
    "high_risk_obstetrics": [("maternalFetalMedicineOrPerinatology", "S", None),
                             ("neonatologyPerinatalMedicine", "P", None), ("gynecologyAndObstetrics", "P", None),
                             ("obstetricsAndMaternityCare", "P", None), ("criticalCareMedicine", "P", None)],
    "nicu": [("neonatologyPerinatalMedicine", "S", "neonatology implies newborn care; NICU beds still need text evidence"),
             ("pediatricCriticalCareMedicine", "P", None), ("pediatrics", "P", None),
             ("maternalFetalMedicineOrPerinatology", "P", None)],
    "picu": [("pediatricCriticalCareMedicine", "S", None), ("pediatricEmergencyMedicine", "P", None),
             ("pediatrics", "P", None), ("neonatologyPerinatalMedicine", "P", None)],
    "icu_critical_care": [("criticalCareMedicine", "S", None), ("pediatricCriticalCareMedicine", "P", None),
                          ("anesthesia", "P", "department-only, over-assigned"), ("anesthesiology", "P", None),
                          ("emergencyMedicine", "P", None), ("pulmonology", "P", None)],
    "ventilator_support": [("criticalCareMedicine", "S", None), ("pediatricCriticalCareMedicine", "S", None),
                           ("neonatologyPerinatalMedicine", "P", None), ("pulmonology", "P", None),
                           ("anesthesia", "P", "department-only, over-assigned"), ("sleepMedicine", "P", "non-invasive ventilation")],
    "cardiac_surgery": [("cardiacSurgery", "S", None), ("cardiothoracicSurgery", "S", None),
                        ("cardiology", "P", "cardiology is medical; does not imply surgery"),
                        ("pediatricCardiology", "P", None), ("vascularSurgery", "P", None)],
    "interventional_cardiology": [("interventionalCardiology", "S", None),
                                  ("cardiology", "P", "many cardiology departments have no cath lab"),
                                  ("pediatricCardiology", "P", None), ("interventionalRadiology", "P", None)],
    "stroke_care": [("vascularNeurology", "S", None), ("cerebrovascularNeurosurgery", "S", None),
                    ("neurology", "P", None), ("neurosurgery", "P", None), ("neuroradiology", "P", None),
                    ("interventionalRadiology", "P", None), ("emergencyMedicine", "P", None)],
    "mri": [(v, "P", NO_MACHINE) for v in RADIOLOGY],
    "ct_scan": [(v, "P", NO_MACHINE) for v in RADIOLOGY],
    "xray": [("radiology", "S", "x-ray is the baseline modality of any radiology department"),
             ("diagnosticRadiology", "S", None), ("cardiothoracicRadiology", "P", None),
             ("pediatricRadiology", "P", None), ("orthopedicSurgery", "P", None)],
    "ultrasound": [("radiology", "S", "ultrasound is near-universal in radiology departments"),
                   ("diagnosticRadiology", "S", None), ("maternalFetalMedicineOrPerinatology", "P", None),
                   ("gynecologyAndObstetrics", "P", None), ("reproductiveEndocrinologyAndInfertility", "P", None),
                   ("cardiology", "P", "echocardiography")],
    "mammography": [("breastImaging", "S", None), ("breastSurgery", "P", None), ("radiology", "P", NO_MACHINE),
                    ("diagnosticRadiology", "P", NO_MACHINE), ("surgicalOncology", "P", None)],
    "nuclear_imaging": [("nuclearMedicineAndMolecularImaging", "S", None), ("nuclearMedicine", "S", None),
                        ("medicalOncology", "P", None), ("radiationOncology", "P", None)],
    "burn_care": [("burnAndTraumaPlasticSurgery", "S", None), ("plasticSurgery", "P", None),
                  ("reconstructivePlasticSurgery", "P", None),
                  ("woundHealingAndDermatologicRegenerativeMedicine", "P", None),
                  ("underseaAndHyperbaricMedicine", "P", None)],
    "trauma_emergency": [("emergencyMedicine", "S", None), ("pediatricEmergencyMedicine", "S", None),
                         ("orthopedicTraumaAndFractureSurgery", "S", None), ("burnAndTraumaPlasticSurgery", "P", None),
                         ("criticalCareMedicine", "P", None), ("generalSurgery", "P", None)],
    "ambulance": [("emergencyMedicine", "P", "no specialty names ambulance service")],
    "chemotherapy": [("medicalOncology", "S", None), ("oncology", "S", None), ("pediatricHematologyOncology", "S", None),
                     ("hematology", "P", None), ("haematology", "P", None), ("gynecologicalOncology", "P", None),
                     ("gynecologicOncology", "P", None), ("neuroOncology", "P", None), ("urologicOncology", "P", None)],
    "radiotherapy": [("radiationOncology", "S", None), ("oncology", "P", None), ("medicalOncology", "P", None)],
    "cancer_surgery": [("surgicalOncology", "S", None), ("gynecologicalOncology", "S", None),
                       ("gynecologicOncology", "S", None), ("urologicOncology", "S", None),
                       ("orthopedicOncology", "S", None), ("neuroOncology", "P", None), ("ocularOncology", "P", None),
                       ("breastSurgery", "P", None), ("headAndNeckSurgeryOtolaryngology", "P", None),
                       ("hepatopancreatobiliarySurgery", "P", None), ("oncology", "P", None)],
    "orthopedic_surgery": [(v, "S", None) for v in
                           ["orthopedicSurgery", "orthopedics", "orthopaedics", "orthopedicTraumaAndFractureSurgery",
                            "shoulderAndElbowOrthopedicSurgery", "footAndAnkleOrthopedicSurgery",
                            "pediatricOrthopedicSurgery", "jointReconstructionSurgery"]]
                          + [(v, "P", None) for v in
                             ["handOrUpperExtremityAndPeripheralNerveSurgery", "handAndUpperExtremitiesSurgery",
                              "handOrUpperExtremitiesSurgery", "orthopedicSportsMedicine"]],
    "joint_replacement": [("jointReconstructionSurgery", "S", None), ("jointReplacementSurgery", "S", None),
                          ("orthopedicSurgery", "P", None), ("orthopedics", "P", None), ("orthopaedics", "P", None),
                          ("shoulderAndElbowOrthopedicSurgery", "P", None)],
    "neurosurgery": [("neurosurgery", "S", None), ("spineNeurosurgery", "S", None), ("skullBaseNeurosurgery", "S", None),
                     ("cerebrovascularNeurosurgery", "S", None), ("pediatricNeurosurgery", "S", None),
                     ("neurology", "P", "neurology is medical; does not imply surgery")],
    "spine_surgery": [("spineNeurosurgery", "S", None), ("orthopedicSpineSurgery", "S", None),
                      ("neurosurgery", "P", None), ("orthopedicSurgery", "P", None), ("spinalCordInjuryMedicine", "P", None)],
    "general_surgery": [(v, "S", None) for v in
                        ["generalSurgery", "colorectalSurgery", "bariatricSurgery", "hepatopancreatobiliarySurgery",
                         "upperGIAndForegutSurgery", "gastrointestinalSurgery", "surgicalGastroenterology",
                         "endocrineSurgery", "pediatricSurgery", "paediatricSurgery"]]
                       + [(v, "P", None) for v in
                          ["minimallyInvasiveSurgeryAndEndourology", "breastSurgery", "vascularSurgery",
                           "generalThoracicSurgery"]]
                       + [("anesthesia", "P", "department-only, over-assigned")],
    "gi_endoscopy": [("gastroenterology", "S", "endoscopy is the core gastroenterology procedure"),
                     ("surgicalGastroenterology", "S", None), ("hepatology", "P", None),
                     ("pediatricGastroenterology", "P", None), ("upperGIAndForegutSurgery", "P", None),
                     ("colorectalSurgery", "P", None)],
    "pulmonology_respiratory": [("pulmonology", "S", None), ("pulmonaryMedicine", "S", None),
                                ("pediatricPulmonology", "S", None), ("sleepMedicine", "P", None),
                                ("sleepMedicineOtolaryngology", "P", None), ("allergyAndImmunology", "P", None),
                                ("cardiothoracicSurgery", "P", None), ("generalThoracicSurgery", "P", None)],
    "transplant": [("transplantSurgery", "S", None), ("renalTransplantationUrology", "S", None),
                   ("boneMarrowTransplant", "S", None), ("hepatopancreatobiliarySurgery", "P", None),
                   ("nephrology", "P", None), ("hepatology", "P", None), ("hematology", "P", None)],
    "blood_bank": [("hematology", "P", "no specialty names a blood bank"), ("haematology", "P", None),
                   ("pathology", "P", None), ("clinicalPathology", "P", None)],
    "laboratory_pathology": [(v, "S", None) for v in
                             ["pathology", "clinicalPathology", "anatomicPathology", "histopathology",
                              "microbiology", "biochemistry"]]
                            + [("oralPathology", "P", None), ("hematology", "P", None)],
    "dental": [(v, "S", None) for v in
               ["dentistry", "generalDentistry", "endodontics", "orthodontics", "prosthodontics", "periodontics",
                "pediatricDentistry", "pedodontics", "aestheticDentistry", "cosmeticDentistry",
                "oralAndMaxillofacialSurgery", "dentoalveolarSurgery", "dentalImplants", "implantology",
                "restorativeDentistry", "laserDentistry", "preventiveDentistry", "oralMedicine"]]
              + [(v, "P", None) for v in
                 ["dentalAnesthesia", "oralPathology", "orthognathicSurgery",
                  "craniofacialAndCleftOralMaxillofacialSurgery", "cosmeticMaxillofacialSurgery"]],
    "eye_surgery": [(v, "S", None) for v in
                    ["cataractAndAnteriorSegmentSurgery", "retinaAndVitreoretinalOphthalmology",
                     "corneaOphthalmology", "glaucomaOphthalmology", "refractiveSurgeryOphthalmology",
                     "oculoplasticsAndReconstructiveOrbitalSurgery"]]
                   + [("ophthalmology", "P", "general ophthalmology; cataract surgery common but not certain")]
                   + [(v, "P", None) for v in
                      ["pediatricsAndStrabismusOphthalmology", "pediatricOphthalmology", "ocularOncology",
                       "eyeTraumaAndEmergencyEyeCare"]],
    "ophthalmology_medical": [(v, "S", None) for v in
                              ["ophthalmology", "neuroOphthalmology", "uveitisOphthalmology", "pediatricOphthalmology",
                               "pediatricsAndStrabismusOphthalmology"]]
                             + [(v, "P", None) for v in
                                ["glaucomaOphthalmology", "retinaAndVitreoretinalOphthalmology", "corneaOphthalmology"]],
    "physiotherapy_rehab": [(v, "S", None) for v in
                            ["physicalMedicineAndRehabilitation", "physiotherapy", "sportsMedicinePMR",
                             "pediatricRehabilitationMedicine", "occupationalAndVocationalRehabilitation"]]
                           + [(v, "P", None) for v in
                              ["neuromuscularMedicinePMR", "painMedicinePMR", "spinalCordInjuryMedicine",
                               "amputeeAndProstheticsAndOrthoticsRehabilitation", "orthopedicSportsMedicine"]],
    "mental_health": [(v, "S", None) for v in
                      ["psychiatry", "addictionPsychiatry", "childAndAdolescentPsychiatry", "geriatricPsychiatry",
                       "neuropsychiatry", "addictionMedicinePM"]]
                     + [(v, "P", None) for v in
                        ["psychology", "clinicalPsychology", "developmental–behavioralPediatrics",
                         "pediatricNeurodevelopmentalDisabilities"]],
    "outpatient_opd": [(v, "P", "OPD is a care format; any clinical specialty implies some OPD, none is strong backing")
                       for v in ["internalMedicine", "familyMedicine", "generalMedicine", "geriatricsInternalMedicine",
                                 "adolescentMedicine", "preventiveMedicine",
                                 "chronicDiseasePreventionAndLifestyleMedicine"]],
    "infertility_ivf": [("reproductiveEndocrinologyAndInfertility", "S", None),
                        ("andrologyAndMaleFertility", "S", None), ("andrology", "P", None),
                        ("gynecologyAndObstetrics", "P", None)],
    "dermatology": [(v, "S", None) for v in
                    ["dermatology", "cosmeticDermatology", "pediatricDermatology", "proceduralDermatology",
                     "hairAndNailDisorders"]]
                   + [("cosmetology", "P", None), ("woundHealingAndDermatologicRegenerativeMedicine", "P", None)],
    "ent": [(v, "S", None) for v in
            ["otolaryngology", "ent", "headAndNeckSurgeryOtolaryngology", "pediatricOtolaryngology", "laryngology",
             "rhinology", "neurotologyAndOtology"]]
           + [("sleepMedicineOtolaryngology", "P", None), ("audiology", "P", None)],
    "pediatrics": [(v, "S", None) for v in
                   ["pediatrics", "neonatologyPerinatalMedicine", "pediatricCriticalCareMedicine",
                    "pediatricEmergencyMedicine"]]
                  + [(v, "P", "pediatric subspecialty") for v in
                     ["pediatricCardiology", "pediatricSurgery", "adolescentMedicine",
                      "developmental–behavioralPediatrics", "pediatricEndocrinology", "pediatricGastroenterology",
                      "pediatricNephrology", "pediatricNeurology", "childNeurology", "pediatricPulmonology",
                      "pediatricHematologyOncology", "pediatricInfectiousDiseases", "maternalAndChildHealth"]],
    "obstetrics_maternity": [(v, "S", None) for v in OBS + ["maternalFetalMedicineOrPerinatology"]]
                            + [(v, "P", None) for v in
                               ["maternalAndChildHealth", "gynecology", "familyPlanningAndComplexContraception",
                                "menopauseAndMidlifeHealth", "urogynecologyAndReconstructivePelvisSurgery"]],
    "cosmetic_aesthetic": [(v, "S", None) for v in
                           ["aestheticAndCosmeticSurgery", "cosmeticSurgery", "cosmeticDermatology", "cosmetology"]]
                          + [(v, "P", None) for v in
                             ["plasticSurgery", "reconstructivePlasticSurgery", "cosmeticMaxillofacialSurgery",
                              "aestheticDentistry", "cosmeticDentistry", "hairAndNailDisorders"]],
    "prosthetics_orthotics": [("amputeeAndProstheticsAndOrthoticsRehabilitation", "S", None),
                              ("podiatry", "P", None), ("podiatricDiabeticLimbSalvageAndWoundCare", "P", None),
                              ("physicalMedicineAndRehabilitation", "P", None), ("orthopedicSurgery", "P", None)],
    "nephrology_renal": [("nephrology", "S", None), ("pediatricNephrology", "S", None),
                         ("renalTransplantationUrology", "P", None), ("urology", "P", None)],
    "gastroenterology": [("gastroenterology", "S", None), ("hepatology", "S", None),
                         ("pediatricGastroenterology", "S", None), ("surgicalGastroenterology", "S", None),
                         ("hepatopancreatobiliarySurgery", "P", None), ("gastrointestinalSurgery", "P", None)],
    "other_clinical": [],
    # --- pa_single_v2 labels ---
    "urology": [("urology", "S", None), ("pediatricUrology", "S", None),
                ("minimallyInvasiveSurgeryAndEndourology", "P", "endourology is mostly stone/prostate work, but the term also covers general laparoscopy"),
                ("urologicOncology", "P", "cancer subspecialty; cancer surgery has its own label"),
                ("andrologyAndMaleFertility", "P", None), ("andrology", "P", None),
                ("renalTransplantationUrology", "P", None),
                ("urogynecologyAndReconstructivePelvisSurgery", "P", None), ("nephrology", "P", None)],
    "diabetes_endocrinology": [("endocrinologyAndDiabetesAndMetabolism", "S", None), ("diabetology", "S", None),
                               ("endocrinology", "S", None), ("pediatricEndocrinology", "S", None),
                               ("endocrineSurgery", "P", "thyroid surgery; implies thyroid care"),
                               ("podiatricDiabeticLimbSalvageAndWoundCare", "P", "diabetic foot care"),
                               ("podiatry", "P", None),
                               ("chronicDiseasePreventionAndLifestyleMedicine", "P", None),
                               ("internalMedicine", "P", "department-only, over-assigned")],
    "health_checkup_vaccination": [("preventiveMedicine", "P", "no specialty names check-up packages or vaccination; department-only, over-assigned"),
                                   ("chronicDiseasePreventionAndLifestyleMedicine", "P", None),
                                   ("familyMedicine", "P", "department-only, over-assigned")],
    "cardiac_diagnostics": [("cardiology", "S", "cardiology department runs echo, TMT and consultations; still a department, not proof of a test"),
                            ("pediatricCardiology", "S", None), ("interventionalCardiology", "P", None),
                            ("internalMedicine", "P", "department-only, over-assigned")],
    "neurology": [("neurology", "S", None), ("headacheMedicine", "S", None), ("epilepsyNeurology", "S", None),
                  ("clinicalNeurophysiology", "S", None), ("pediatricNeurology", "S", None),
                  ("childNeurology", "S", None), ("cognitiveAndBehavioralNeurology", "S", None),
                  ("brainInjuryNeurology", "P", None), ("vascularNeurology", "P", "stroke has its own label"),
                  ("neurosurgery", "P", "neurosurgery is surgical; does not imply a neurology clinic"),
                  ("sleepMedicine", "P", None)],
    "ayush_traditional_medicine": [],  # no AYUSH specialty term reaches 20 facilities
    "gynecology": [(v, "S", "obstetrics and gynaecology department covers non-pregnancy gynaecology") for v in OBS
                   if v != "obstetricsAndMaternityCare"]
                  + [("gynecology", "S", None), ("gynecologicalSurgery", "S", None),
                     ("menopauseAndMidlifeHealth", "S", None),
                     ("urogynecologyAndReconstructivePelvisSurgery", "S", None),
                     ("obstetricsAndMaternityCare", "P", "maternity-only term"),
                     ("familyPlanningAndComplexContraception", "P", None),
                     ("reproductiveEndocrinologyAndInfertility", "P", "fertility has its own label"),
                     ("gynecologicalOncology", "P", "cancer subspecialty"), ("gynecologicOncology", "P", None)],
    "proctology": [("colorectalSurgery", "S", None), ("generalSurgery", "P", "general surgeons often treat piles; not proof"),
                   ("surgicalGastroenterology", "P", None), ("gastroenterology", "P", None)],
    "pain_management": [("painMedicinePMR", "S", None), ("painManagement", "S", None),
                        ("anesthesiology", "P", "pain clinics are often run by anaesthetists"),
                        ("anesthesia", "P", "department-only, over-assigned"),
                        ("physicalMedicineAndRehabilitation", "P", None)],
    "vascular_surgery": [("vascularSurgery", "S", None),
                         ("cardiothoracicSurgery", "P", None), ("interventionalRadiology", "P", None),
                         ("generalSurgery", "P", "general surgeons treat varicose veins; not proof")],
    "cardiology_medical": [("cardiology", "S", "cardiology department = general heart care"),
                           ("pediatricCardiology", "S", None), ("interventionalCardiology", "P", None),
                           ("internalMedicine", "P", "department-only, over-assigned")],
}

# implied_by_service: SERVICE <- [(other service whose evidence implies SERVICE is possible, strength, note)]
IMPLIED = {
    "dialysis": [("nephrology_renal", "S", "nephrology services usually include dialysis"),
                 ("transplant", "P", "renal transplant needs dialysis support"),
                 ("icu_critical_care", "P", "ICUs often run CRRT / bedside dialysis")],
    "caesarean_section": [("obstetrics_maternity", "S", "obstetric units perform C-sections"),
                          ("high_risk_obstetrics", "S", None), ("normal_delivery", "P", None), ("nicu", "P", None)],
    "normal_delivery": [("obstetrics_maternity", "S", None), ("caesarean_section", "S", None),
                        ("high_risk_obstetrics", "S", None)],
    "high_risk_obstetrics": [("nicu", "P", None), ("caesarean_section", "P", None), ("icu_critical_care", "P", None)],
    "nicu": [("picu", "P", None), ("high_risk_obstetrics", "P", "high-risk deliveries need newborn intensive care")],
    "picu": [("nicu", "P", None), ("icu_critical_care", "P", None)],
    "icu_critical_care": [("ventilator_support", "S", None), ("cardiac_surgery", "S", "post-op cardiac ICU required"),
                          ("transplant", "S", None), ("neurosurgery", "P", None), ("trauma_emergency", "P", None),
                          ("picu", "P", None), ("nicu", "P", None)],
    "ventilator_support": [("icu_critical_care", "S", None), ("nicu", "S", None), ("picu", "S", None)],
    "cardiac_surgery": [("interventional_cardiology", "P", None)],
    "interventional_cardiology": [("cardiac_surgery", "S", "cardiac surgical centres almost always have a cath lab")],
    "stroke_care": [("neurosurgery", "P", None), ("mri", "P", None), ("ct_scan", "P", None),
                    ("icu_critical_care", "P", None)],
    "mri": [("neurosurgery", "P", None), ("stroke_care", "P", None), ("spine_surgery", "P", None)],
    "ct_scan": [("trauma_emergency", "P", None), ("neurosurgery", "P", None), ("stroke_care", "P", None),
                ("mri", "P", "MRI sites usually also have CT")],
    "xray": [("orthopedic_surgery", "P", None), ("trauma_emergency", "P", None), ("ct_scan", "P", None)],
    "ultrasound": [("obstetrics_maternity", "P", None), ("infertility_ivf", "P", None)],
    "mammography": [("cancer_surgery", "P", None)],
    "nuclear_imaging": [("chemotherapy", "P", None), ("radiotherapy", "P", None)],
    "burn_care": [("trauma_emergency", "P", None), ("icu_critical_care", "P", None)],
    "trauma_emergency": [("icu_critical_care", "P", None), ("ambulance", "P", None), ("burn_care", "P", None)],
    "ambulance": [("trauma_emergency", "P", None), ("icu_critical_care", "P", None)],
    "chemotherapy": [("radiotherapy", "P", None), ("cancer_surgery", "P", None)],
    "radiotherapy": [("chemotherapy", "P", None), ("nuclear_imaging", "P", None)],
    "cancer_surgery": [("chemotherapy", "P", None), ("radiotherapy", "P", None)],
    "orthopedic_surgery": [("joint_replacement", "S", "joint replacement is orthopaedic surgery"),
                           ("spine_surgery", "P", None), ("trauma_emergency", "P", None)],
    "joint_replacement": [("orthopedic_surgery", "P", None)],
    "neurosurgery": [("spine_surgery", "P", None), ("stroke_care", "P", None)],
    "spine_surgery": [("neurosurgery", "P", None), ("orthopedic_surgery", "P", None)],
    "general_surgery": [("cancer_surgery", "P", None), ("gi_endoscopy", "P", None)],
    "gi_endoscopy": [("gastroenterology", "S", None)],
    "pulmonology_respiratory": [("ventilator_support", "P", None)],
    "transplant": [],
    "blood_bank": [("cardiac_surgery", "P", None), ("transplant", "P", None), ("trauma_emergency", "P", None),
                   ("caesarean_section", "P", None), ("chemotherapy", "P", None)],
    "laboratory_pathology": [("blood_bank", "P", None)],
    "dental": [],
    "eye_surgery": [("ophthalmology_medical", "P", None)],
    "physiotherapy_rehab": [("orthopedic_surgery", "P", None), ("joint_replacement", "P", None),
                            ("stroke_care", "P", None)],
    "mental_health": [],
    "outpatient_opd": [],
    "infertility_ivf": [],
    "dermatology": [("cosmetic_aesthetic", "P", None)],
    "ent": [],
    "ophthalmology_medical": [("eye_surgery", "S", None)],
    "pediatrics": [("nicu", "P", None), ("picu", "P", None)],
    "obstetrics_maternity": [("normal_delivery", "S", None), ("caesarean_section", "S", None),
                             ("high_risk_obstetrics", "S", None)],
    "cosmetic_aesthetic": [],
    "prosthetics_orthotics": [],
    "nephrology_renal": [("dialysis", "S", "a dialysis unit is a nephrology service"), ("transplant", "P", None)],
    "gastroenterology": [("gi_endoscopy", "S", None)],
    "other_clinical": [],
    # --- pa_single_v2 labels ---
    "urology": [("nephrology_renal", "P", None), ("transplant", "P", None)],
    "diabetes_endocrinology": [],
    "health_checkup_vaccination": [("laboratory_pathology", "P", None), ("pediatrics", "P", "child immunisation")],
    # no implied links: a cardiac_surgery / interventional claim + cardiology department made
    # ~960 Possible rows from department lists; removed on review
    "cardiac_diagnostics": [],
    "neurology": [("stroke_care", "P", None), ("neurosurgery", "P", None)],
    "ayush_traditional_medicine": [],
    "gynecology": [("obstetrics_maternity", "P", None), ("infertility_ivf", "P", None)],
    "proctology": [("general_surgery", "P", None)],
    "pain_management": [("physiotherapy_rehab", "P", None), ("orthopedic_surgery", "P", None)],
    "vascular_surgery": [("dialysis", "P", "dialysis access (AV fistula) is vascular surgery")],
    "cardiology_medical": [],  # implied links removed on review (same reason as cardiac_diagnostics)
}

# ---------------------------------------------------------------------------
# service_type_fit source
# ---------------------------------------------------------------------------
ALL = set(SERVICES)
T = {}


def spec(default, expected=(), plausible=(), unexpected=(), why=""):
    return {"default": default, "expected": set(expected), "plausible": set(plausible),
            "unexpected": set(unexpected), "why": why}


HOSP_CORE = ["icu_critical_care", "ventilator_support", "trauma_emergency", "ambulance", "ct_scan", "xray",
             "ultrasound", "laboratory_pathology", "outpatient_opd", "general_surgery", "orthopedic_surgery",
             "obstetrics_maternity", "normal_delivery", "caesarean_section", "pediatrics", "blood_bank",
             "physiotherapy_rehab", "gi_endoscopy", "pulmonology_respiratory", "gastroenterology", "nephrology_renal",
             "dialysis"]
TYPE_SPEC = {
    "multispecialty_hospital": spec("plausible", HOSP_CORE + ["mri", "interventional_cardiology"],
                                    why="broad hospital"),
    "medical_college_teaching_hospital": spec("plausible", HOSP_CORE + [
        "mri", "nicu", "high_risk_obstetrics", "mental_health", "dental", "ent", "ophthalmology_medical",
        "eye_surgery", "dermatology", "neurosurgery"], why="teaching hospital with mandated departments"),
    "government_health_centre": spec("plausible",
                                     ["outpatient_opd", "normal_delivery", "obstetrics_maternity", "pediatrics",
                                      "laboratory_pathology"],
                                     unexpected=["cardiac_surgery", "transplant", "radiotherapy", "nuclear_imaging",
                                                 "infertility_ivf", "cosmetic_aesthetic"],
                                     why="PHC/CHC up to district hospital; tertiary services unexpected"),
    "general_hospital_or_nursing_home": spec("plausible",
                                             ["outpatient_opd", "laboratory_pathology", "xray", "ultrasound",
                                              "general_surgery", "normal_delivery", "caesarean_section",
                                              "obstetrics_maternity", "pediatrics"],
                                             unexpected=["transplant", "radiotherapy", "nuclear_imaging"],
                                             why="general hospital / nursing home"),
    "maternity_women_children": spec("unexpected",
                                     ["normal_delivery", "caesarean_section", "high_risk_obstetrics",
                                      "obstetrics_maternity", "nicu", "pediatrics", "ultrasound", "outpatient_opd",
                                      "laboratory_pathology"],
                                     ["picu", "infertility_ivf", "mammography", "icu_critical_care",
                                      "ventilator_support", "blood_bank", "ambulance", "general_surgery",
                                      "cancer_surgery", "physiotherapy_rehab", "trauma_emergency",
                                      "cosmetic_aesthetic"], why="maternity / women and children"),
    "pediatric": spec("unexpected", ["pediatrics", "nicu", "picu", "outpatient_opd", "laboratory_pathology"],
                      ["ventilator_support", "icu_critical_care", "ultrasound", "general_surgery", "ambulance",
                       "trauma_emergency", "physiotherapy_rehab", "mental_health", "dental", "ent",
                       "ophthalmology_medical", "dermatology", "pulmonology_respiratory", "gastroenterology",
                       "nephrology_renal", "blood_bank", "ct_scan", "mri", "orthopedic_surgery", "neurosurgery",
                       "cardiac_surgery", "interventional_cardiology", "dialysis", "chemotherapy"],
                      why="children's hospital/clinic"),
    "eye": spec("unexpected", ["eye_surgery", "ophthalmology_medical", "outpatient_opd"],
                ["ultrasound", "cosmetic_aesthetic", "cancer_surgery"], why="eye facility (B-scan, oculoplastics, ocular oncology plausible)"),
    "dental": spec("unexpected", ["dental", "outpatient_opd"], ["cosmetic_aesthetic"], why="dental facility"),
    "ent_hearing_speech": spec("unexpected", ["ent", "outpatient_opd"],
                               ["cosmetic_aesthetic", "cancer_surgery", "pulmonology_respiratory",
                                "physiotherapy_rehab"], why="ENT / hearing / speech"),
    "skin_hair_cosmetic": spec("unexpected", ["dermatology", "cosmetic_aesthetic", "outpatient_opd"], ["dental"],
                               why="skin / hair / cosmetic"),
    "ivf_fertility": spec("unexpected", ["infertility_ivf", "outpatient_opd", "ultrasound", "laboratory_pathology"],
                          ["obstetrics_maternity", "high_risk_obstetrics", "normal_delivery", "caesarean_section",
                           "general_surgery", "nicu"], why="IVF / fertility"),
    "kidney_urology": spec("unexpected",
                           ["nephrology_renal", "dialysis", "outpatient_opd", "laboratory_pathology", "ultrasound"],
                           ["transplant", "general_surgery", "ct_scan", "icu_critical_care", "cancer_surgery",
                            "infertility_ivf", "ambulance"], why="kidney / urology"),
    "cardiac": spec("unexpected", ["cardiac_surgery", "interventional_cardiology", "icu_critical_care",
                                   "outpatient_opd", "laboratory_pathology", "ultrasound", "xray"],
                    ["ventilator_support", "ct_scan", "mri", "nuclear_imaging", "trauma_emergency", "ambulance",
                     "blood_bank", "stroke_care", "transplant", "physiotherapy_rehab", "pulmonology_respiratory"],
                    why="cardiac centre"),
    "cancer": spec("unexpected", ["chemotherapy", "radiotherapy", "cancer_surgery", "outpatient_opd",
                                  "laboratory_pathology", "ct_scan"],
                   ["mri", "nuclear_imaging", "mammography", "ultrasound", "icu_critical_care",
                    "ventilator_support", "blood_bank", "transplant", "gi_endoscopy", "physiotherapy_rehab",
                    "general_surgery"], why="cancer centre"),
    "orthopedic_spine": spec("unexpected", ["orthopedic_surgery", "joint_replacement", "spine_surgery",
                                            "physiotherapy_rehab", "xray", "outpatient_opd"],
                             ["trauma_emergency", "mri", "ct_scan", "laboratory_pathology", "prosthetics_orthotics",
                              "neurosurgery", "icu_critical_care", "ambulance", "ultrasound", "cancer_surgery"],
                             why="orthopaedic / spine"),
    "neuro": spec("unexpected", ["neurosurgery", "stroke_care", "outpatient_opd", "mri", "ct_scan"],
                  ["spine_surgery", "icu_critical_care", "ventilator_support", "trauma_emergency",
                   "physiotherapy_rehab", "mental_health", "laboratory_pathology", "ambulance", "cancer_surgery"],
                  why="neuro centre"),
    "gastro_liver": spec("unexpected", ["gastroenterology", "gi_endoscopy", "outpatient_opd", "laboratory_pathology",
                                        "ultrasound"],
                         ["general_surgery", "cancer_surgery", "transplant", "ct_scan", "mri", "icu_critical_care",
                          "blood_bank", "chemotherapy"], why="gastro / liver"),
    "diagnostic_imaging_lab": spec("unexpected", ["mri", "ct_scan", "xray", "ultrasound", "mammography",
                                                  "laboratory_pathology"],
                                   ["nuclear_imaging", "outpatient_opd"],
                                   why="imaging / lab only; no treatment or surgery"),
    "physiotherapy_rehab": spec("unexpected", ["physiotherapy_rehab", "outpatient_opd"], ["prosthetics_orthotics"],
                                why="physiotherapy / rehab"),
    "mental_health_deaddiction": spec("unexpected", ["mental_health", "outpatient_opd"], [],
                                      why="mental health / de-addiction"),
    "ayush_alternative": spec("unexpected", ["outpatient_opd"], ["physiotherapy_rehab", "dermatology"],
                              why="AYUSH / alternative medicine; allopathic procedures unexpected"),
    "home_care_or_ambulance": spec("unexpected", ["ambulance"],
                                   ["physiotherapy_rehab", "outpatient_opd", "icu_critical_care",
                                    "ventilator_support", "dialysis", "trauma_emergency"],
                                   why="home care / ambulance (home ICU, home dialysis plausible)"),
    "general_clinic_polyclinic": spec("unexpected", ["outpatient_opd"],
                                      ["ultrasound", "pediatrics", "dermatology", "ent", "ophthalmology_medical",
                                       "dental", "mental_health", "physiotherapy_rehab", "obstetrics_maternity",
                                       "gastroenterology", "pulmonology_respiratory", "nephrology_renal",
                                       "infertility_ivf", "cosmetic_aesthetic", "gi_endoscopy", "general_surgery"],
                                      why="clinic / polyclinic: consultations, minor procedures"),
    "other_single_specialty": spec("plausible",
                                   unexpected=["transplant", "cardiac_surgery", "nicu", "picu", "caesarean_section",
                                               "normal_delivery", "high_risk_obstetrics", "blood_bank",
                                               "radiotherapy", "neurosurgery"],
                                   why="specialty unknown (diabetes, pulmonology, colorectal, burns...); "
                                       "major-hospital services unexpected"),
    "not_a_care_facility": spec("unexpected", why="not a care facility"),
    "unknown": spec("plausible", why="type unknown"),
}
# pa_single_v2 labels: added to the per-type lists above (types not listed keep their default:
# plausible for broad hospitals / other_single_specialty / unknown, unexpected elsewhere).
NEW_FIT_V2 = {'multispecialty_hospital': {'expected': ['urology', 'cardiac_diagnostics', 'gynecology', 'diabetes_endocrinology', 'neurology', 'health_checkup_vaccination']},
    'medical_college_teaching_hospital': {'expected': ['urology', 'cardiac_diagnostics', 'gynecology', 'diabetes_endocrinology', 'neurology', 'health_checkup_vaccination']},
    'government_health_centre': {'expected': ['health_checkup_vaccination']},
    'general_hospital_or_nursing_home': {'expected': ['gynecology']},
    'maternity_women_children': {'expected': ['gynecology'], 'plausible': ['health_checkup_vaccination', 'diabetes_endocrinology']},
    'pediatric': {'expected': ['health_checkup_vaccination'], 'plausible': ['neurology', 'diabetes_endocrinology', 'urology', 'cardiac_diagnostics']},
    'ent_hearing_speech': {'plausible': ['neurology']},
    'skin_hair_cosmetic': {'plausible': ['ayush_traditional_medicine']},
    'ivf_fertility': {'expected': ['gynecology'], 'plausible': ['urology', 'diabetes_endocrinology']},
    'kidney_urology': {'expected': ['urology'], 'plausible': ['diabetes_endocrinology']},
    'cardiac': {'expected': ['cardiac_diagnostics'], 'plausible': ['diabetes_endocrinology', 'health_checkup_vaccination', 'neurology']},
    'cancer': {'plausible': ['gynecology', 'urology', 'pain_management', 'health_checkup_vaccination', 'proctology']},
    'orthopedic_spine': {'expected': ['pain_management'], 'plausible': ['neurology']},
    'neuro': {'expected': ['neurology'], 'plausible': ['pain_management']},
    'gastro_liver': {'expected': ['proctology'], 'plausible': ['health_checkup_vaccination', 'diabetes_endocrinology']},
    'diagnostic_imaging_lab': {'expected': ['health_checkup_vaccination'], 'plausible': ['cardiac_diagnostics']},
    'physiotherapy_rehab': {'expected': ['pain_management'], 'plausible': ['neurology', 'ayush_traditional_medicine']},
    'mental_health_deaddiction': {'plausible': ['neurology']},
    'ayush_alternative': {'expected': ['ayush_traditional_medicine'], 'plausible': ['pain_management']},
    'home_care_or_ambulance': {'plausible': ['health_checkup_vaccination', 'pain_management']},
    'general_clinic_polyclinic': {'plausible': ['diabetes_endocrinology', 'health_checkup_vaccination', 'cardiac_diagnostics', 'gynecology', 'neurology', 'urology', 'proctology', 'pain_management', 'ayush_traditional_medicine']}}
# vascular_surgery and cardiology_medical (added after the first 9)
for _ft, _lvl, _svc in [
        ("multispecialty_hospital", "expected", "cardiology_medical"),
        ("medical_college_teaching_hospital", "expected", "cardiology_medical"),
        ("medical_college_teaching_hospital", "expected", "vascular_surgery"),
        ("cardiac", "expected", "cardiology_medical"), ("cardiac", "plausible", "vascular_surgery"),
        ("pediatric", "plausible", "cardiology_medical"),
        ("general_clinic_polyclinic", "plausible", "cardiology_medical"),
        ("kidney_urology", "plausible", "vascular_surgery"),
        ("home_care_or_ambulance", "plausible", "cardiology_medical")]:
    NEW_FIT_V2.setdefault(_ft, {}).setdefault(_lvl, []).append(_svc)
for _ft, _lv in NEW_FIT_V2.items():
    for _lvl, _svcs in _lv.items():
        TYPE_SPEC[_ft][_lvl] |= set(_svcs)
NON_CARE = {"not_a_care_facility", "unknown"}
XRAY_NOT_FLOOR = {"eye", "skin_hair_cosmetic", "ivf_fertility", "mental_health_deaddiction",
                  "home_care_or_ambulance", "physiotherapy_rehab", "ayush_alternative", "ent_hearing_speech"}

EXCEPTIONS = {
    ("xray", "dental"): ("plausible", "dental x-ray / OPG is routine in dental clinics"),
    ("cancer_surgery", "dental"): ("unexpected", "oral cancer surgery belongs to hospitals, not dental clinics"),
    ("blood_bank", "diagnostic_imaging_lab"): ("unexpected", "labs collect samples; blood banks are licensed separately"),
    ("dialysis", "general_clinic_polyclinic"): ("unexpected", "standalone dialysis centres are typed kidney_urology"),
    ("burn_care", "other_single_specialty"): ("plausible", "burn centres have no own type and fall here"),
    ("mri", "government_health_centre"): ("plausible", "district hospitals sometimes have MRI (often PPP)"),
    ("dialysis", "cardiac"): ("plausible", "changed after blind validation: cardiac hospitals often run dialysis units"),
}


# ---------------------------------------------------------------------------
# service_terms source: words / phrases that NAME each service (wave 1, proposal 1).
# Used by scripts/build_facility_service.py: Confirmed needs >= 1 non-demoted explicit/stated
# claim sentence matching the service's terms (whole word / phrase, case-insensitive).
# Plain strings are phrases (spaces match space or hyphen); "re:" strings are Java regex.
# HAND_CHECKED: the 8 headline services, reviewed for synonyms and false friends.
# Others: built from the label, readable name and obvious synonyms (source 'generated');
# SYNONYM_PASS: synonyms added after reading demoted quotes (source 'synonym_pass').
# other_clinical has no terms (catch-all) and is never gated.
# ---------------------------------------------------------------------------
HAND_CHECKED = {"dialysis", "caesarean_section", "nicu", "cardiac_surgery", "mri", "burn_care",
                "icu_critical_care", "trauma_emergency"}
TERMS = {
    # --- hand-checked ---
    "cardiac_surgery": [r"re:cardiac\s+surg\w*", r"re:heart\s+surg\w*", "cabg", "ctvs",
                        r"re:coronary\s+(artery\s+)?bypass\w*", r"re:bypass\s+(surg\w*|graft\w*)",
                        r"re:valve\s+(replacement|repair|surg\w*)\w*", r"re:open[\s-]+heart",
                        r"re:cardio[\s-]?thoracic\w*", r"re:cardiothoracic\w*"],
    # not "cardiology" alone, not "operating theatre", not TAVI (interventional)
    "caesarean_section": [r"re:ca?esa?r(e|i|ea|ia)n\w*", r"re:caeserean\w*", r"re:c[\s-]?sections?",
                          "lscs", r"re:operative\s+deliver\w*"],
    "nicu": [r"re:n\.?i\.?c\.?u\.?s?", r"re:neo[\s-]?natal\s+(intensive|icu|critical)\w*",
             r"re:new[\s-]?born\s+(intensive|icu|critical)\w*",
             r"re:level[\s-]*(ii|iii|2|3)\s+(neonatal|nicu|newborn)\w*"],
    # SNCU (special newborn care unit) is NOT NICU and does not match
    "dialysis": [r"re:dialy[sz]\w*", r"re:ha?emo[\s-]?dialy\w*", "capd", "crrt",
                 "renal replacement therapy"],
    "mri": ["mri", r"re:m\.r\.i\.?", "magnetic resonance", "tesla", r"re:\d(\.\d)?\s?t(?![a-z])",
            r"re:mr\s+(scan|imaging|angiograph)\w*"],
    "burn_care": [r"re:burns?\s+(unit|ward|care|cent(re|er)|icu|treatment|management|surg\w*|injur\w*)",
                  r"re:(treat\w*|management|care)\s+of\s+burns?", r"re:burns?\s+(and|&)\s+(plastic|trauma)\w*"],
    "icu_critical_care": [r"re:i\.?c\.?u\.?s?", "iccu", "ccu", "micu", "sicu", "cticu",
                          "intensive care", "critical care"],
    "trauma_emergency": [r"re:emergency\s+(department|room|ward|unit|services?|care|medicine|cent(re|er))",
                         "casualty", r"re:trauma\s+(care|cent(re|er)|unit|ward|team|services?|surg\w*|icu)",
                         r"re:accident\s+(and|&)\s+emergency", r"re:a\s?&\s?e", "polytrauma"],
    # --- generated (not hand-checked) ---
    "normal_delivery": [r"re:normal\s+deliver\w*", r"re:vaginal\s+(deliver\w*|birth)", r"re:deliver(y|ies)",
                        "labour room", "labor room", "childbirth", "painless delivery", "birthing"],
    "high_risk_obstetrics": [r"re:high[\s-]+risk\s+(pregnan\w*|obstetric\w*|deliver\w*)",
                             r"re:maternal[\s-]+fetal\s+medicine", "perinatology", "fetal medicine"],
    "picu": [r"re:p\.?i\.?c\.?u\.?s?", r"re:(paediatric|pediatric)\s+(intensive|icu|critical)\w*"],
    "ventilator_support": [r"re:ventilat\w*", "bipap", "cpap", "life support"],
    "interventional_cardiology": [r"re:angioplast\w*", r"re:angiograph\w*", r"re:angiogram\w*",
                                  r"re:cath(eterisation|eterization)?\s*lab\w*", "cathlab", "ptca",
                                  r"re:stent\w*", r"re:pacemaker\w*", "tavi", "tavr",
                                  "interventional cardiology"],
    "stroke_care": [r"re:strokes?", "thrombolysis", "thrombectomy", "brain attack"],
    "ct_scan": [r"re:ct(\s+scan\w*)?", r"re:c\.t\.", "cat scan", "computed tomography",
                r"re:\d+[\s-]*slice\w*"],
    "xray": [r"re:x[\s-]?rays?", r"re:radiograph\w*", "dr system", "cr system"],
    "ultrasound": [r"re:ultrasound\w*", r"re:ultrasonograph\w*", "usg", r"re:sonograph\w*",
                   r"re:doppler\w*", r"re:color\s+doppler"],
    "mammography": [r"re:mammogra\w*"],
    "nuclear_imaging": [r"re:pet[\s-]?ct", r"re:pet\s+scan\w*", "spect", r"re:nuclear\s+(medicine|imaging|scan\w*)",
                        "gamma camera", r"re:bone\s+scan\w*"],
    "ambulance": [r"re:ambulances?"],
    "chemotherapy": [r"re:chemo\w*", "immunotherapy", "targeted therapy", "day care oncology"],
    "radiotherapy": [r"re:radiotherap\w*", r"re:radiation\s+(therap\w*|oncology)", r"re:linac\w*",
                     r"re:linear\s+accelerator\w*", r"re:brachytherap\w*", "cyberknife", "tomotherapy",
                     "gamma knife"],
    "cancer_surgery": [r"re:(cancer|onco|tumou?r)\w*\s+surg\w*", r"re:surgical\s+oncolog\w*", "oncosurgery",
                       r"re:mastectom\w*", r"re:\w*ectomy\s+for\s+cancer", r"re:tumou?r\s+(removal|excision|resection)"],
    "orthopedic_surgery": [r"re:orthop(a)?edic\w*", r"re:fractur\w*", r"re:arthroscop\w*", r"re:bone\s+surg\w*",
                           "ligament reconstruction", "acl reconstruction"],
    "joint_replacement": [r"re:(joint|knee|hip|shoulder)\s+replacement\w*", r"re:arthroplast\w*", "tkr", "thr"],
    "neurosurgery": [r"re:neuro[\s-]?surg\w*", r"re:brain\s+(surg\w*|tumou?r)", r"re:cranio\w*",
                     "skull base"],
    "spine_surgery": [r"re:spin(e|al)\s+surg\w*", r"re:discectom\w*", r"re:laminectom\w*",
                      r"re:spinal\s+fusion", r"re:endoscopic\s+spine"],
    "general_surgery": [r"re:general\s+surg\w*", r"re:laparoscop\w*", r"re:hernia\w*", r"re:appendic\w*",
                        r"re:gall\s?bladder", r"re:cholecystectom\w*", r"re:surger(y|ies)"],
    "gi_endoscopy": [r"re:endoscop\w*", r"re:colonoscop\w*", r"re:gastroscop\w*", "ercp", "eus",
                     r"re:sigmoidoscop\w*"],
    "pulmonology_respiratory": [r"re:pulmon\w*", r"re:respirat\w*", r"re:chest\s+(medicine|physician|diseases?)",
                                r"re:bronchoscop\w*", "spirometry", "pft", "lung function",
                                r"re:sleep\s+(study|studies|lab)", r"re:asthma\w*", "copd", "tuberculosis"],
    "transplant": [r"re:transplant\w*"],
    "blood_bank": [r"re:blood\s+(bank|storage|transfusion)\w*", "blood component"],
    "laboratory_pathology": [r"re:laborator(y|ies)", r"re:lab(s)?", r"re:patholog\w*", r"re:blood\s+tests?",
                             r"re:diagnostic\s+tests?", "biochemistry", "microbiology", "haematology",
                             "hematology", r"re:sample\s+collection"],
    "dental": [r"re:dent\w*", r"re:teeth", r"re:tooth", r"re:orthodont\w*", "root canal", r"re:implants?",
               r"re:oral\s+(surg\w*|care)", "braces", "aligners", "maxillofacial"],
    "eye_surgery": [r"re:cataract\w*", "lasik", r"re:retina\w*", r"re:vitreo\w*", r"re:glaucoma\w*",
                    r"re:cornea\w*", r"re:phaco\w*", r"re:eye\s+surg\w*", "squint", r"re:oculoplast\w*"],
    "physiotherapy_rehab": [r"re:physio\w*", r"re:rehabilit\w*", "occupational therapy",
                            r"re:physical\s+(therapy|medicine)"],
    "mental_health": [r"re:psychiatr\w*", r"re:psycholog\w*", r"re:mental\s+health", r"re:de[\s-]?addiction",
                      "counselling", "counseling", r"re:depression", "anxiety"],
    "outpatient_opd": [r"re:opd\w*", r"re:out[\s-]?patient\w*", r"re:consult\w*", r"re:general\s+(medicine|physician)",
                       r"re:internal\s+medicine", r"re:fever\w*", "family medicine", r"re:clinic\w*"],
    "infertility_ivf": [r"re:ivf", r"re:infertil\w*", r"re:fertility", r"re:iui", r"re:icsi",
                        r"re:test[\s-]?tube", "embryo", r"re:assisted\s+reproduct\w*"],
    "dermatology": [r"re:dermat\w*", r"re:skin\w*", r"re:acne", "psoriasis", "vitiligo", r"re:hair\s+(loss|fall)"],
    "ent": [r"re:\bent\b", r"re:e\.n\.t", r"re:otolaryng\w*", r"re:otorhino\w*", r"re:ear,?\s+nose",
            r"re:sinus\w*", r"re:tonsil\w*", r"re:cochlear\w*", r"re:audiolog\w*", r"re:hearing"],
    "ophthalmology_medical": [r"re:ophthalm\w*", r"re:eye\s+(care|check\w*|clinic|exam\w*|test\w*)",
                              r"re:optometr\w*", r"re:spectacle\w*", r"re:vision", r"re:contact\s+lens\w*"],
    "pediatrics": [r"re:p(a)?ediatric\w*", r"re:child(ren)?('s)?\s+(care|health|specialist|clinic|hospital)",
                   r"re:new[\s-]?born\s+care", r"re:neonat\w*", "child care", r"re:p(a)?ediatrician\w*"],
    "obstetrics_maternity": [r"re:obstetric\w*", r"re:maternity", r"re:antenatal", r"re:prenatal",
                             r"re:postnatal", r"re:pregnan\w*", r"re:labou?r\s+room", r"re:deliver(y|ies)",
                             r"re:gyn(a)?ecolog\w*"],
    "cosmetic_aesthetic": [r"re:cosmet\w*", r"re:aesthet\w*", r"re:esthet\w*", r"re:liposuc\w*",
                           r"re:rhinoplast\w*", "botox", r"re:hair\s+transplant\w*", r"re:fillers?",
                           r"re:plastic\s+surg\w*", r"re:laser\s+hair"],
    "prosthetics_orthotics": [r"re:prosthe\w*", r"re:orthotic\w*", r"re:artificial\s+limb\w*", r"re:calipers?",
                              r"re:braces"],
    "nephrology_renal": [r"re:nephrolog\w*", r"re:kidney\w*", r"re:renal"],
    "gastroenterology": [r"re:gastro\w*", r"re:hepatolog\w*", r"re:liver", r"re:digestive"],
    "urology": [r"re:urolog\w*", r"re:kidney\s+stones?", r"re:stones?", r"re:prostat\w*", r"re:lithotrip\w*",
                "turp", "pcnl", "urs", "rirs", r"re:cystoscop\w*", r"re:uroflow\w*", r"re:circumcis\w*",
                r"re:androlog\w*", "holep"],
    "diabetes_endocrinology": [r"re:diabet\w*", r"re:thyroid\w*", r"re:endocrin\w*", r"re:insulin\w*",
                               r"re:hormon\w*"],
    "health_checkup_vaccination": [r"re:check[\s-]?ups?", r"re:health\s+(check\w*|packages?|screening)",
                                   r"re:vaccin\w*", r"re:immuni[sz]\w*", r"re:screening", r"re:medical\s+exam\w*"],
    "cardiac_diagnostics": [r"re:echo\w*", r"re:2d\s+echo", "tmt", r"re:treadmill\w*", r"re:stress\s+test\w*",
                            r"re:holter\w*", "eecp", r"re:doppler\w*", "ambulatory blood pressure"],
    "neurology": [r"re:neurolog\w*", r"re:epilep\w*", r"re:migraine\w*", r"re:headache\w*", r"re:vertigo",
                  r"re:parkinson\w*", r"re:dementia", r"re:neuropath\w*", "eeg", "emg", "ncv",
                  r"re:nerve\s+conduction"],
    "ayush_traditional_medicine": [r"re:ayurved\w*", r"re:homo?eopath\w*", r"re:panchakarma\w*", r"re:unani",
                                   r"re:siddha", r"re:naturopath\w*", r"re:yoga\w*", r"re:shirodhara",
                                   r"re:kshar\w*", "ayush"],
    "gynecology": [r"re:gyn(a)?ecolog\w*", r"re:hysteroscop\w*", r"re:colposcop\w*", r"re:pap\s+smear\w*",
                   r"re:pco[sd]", r"re:fibroid\w*", r"re:endometrio\w*", r"re:hysterectom\w*",
                   r"re:menopaus\w*", r"re:contracept\w*", r"re:tubectom\w*", "mtp"],
    "proctology": [r"re:piles", r"re:fistula\w*", r"re:fissure\w*", r"re:ha?emorrhoid\w*", r"re:proctolog\w*",
                   r"re:pilonidal", r"re:ano[\s-]?rectal"],
    "pain_management": [r"re:pain\w*", r"re:nerve\s+blocks?"],
    "vascular_surgery": [r"re:vascular\w*", r"re:varicose\w*", r"re:av\s+fistula\w*", r"re:sclerotherap\w*",
                         r"re:endovenous\w*", r"re:vein\w*", r"re:arter\w*"],
    "cardiology_medical": [r"re:cardiolog\w*", r"re:heart\w*", r"re:cardiac\w*"],
    "other_clinical": [],
}
# Filled after reading the demoted non-theatre quotes of services whose Confirmed rows would lose
# > 30% under the term gate (neurosurgery, obstetrics_maternity, orthopedic_surgery). Most demoted
# quotes were operating-theatre lines, which are not synonyms and were not added.
SYNONYM_PASS = {
    "neurosurgery": [r"re:spin(e|al)\s+surg\w*", r"re:(vp\s+)?shunt\w*", r"re:ventriculo\w*",
                     r"re:hydrocephal\w*", r"re:deep\s+brain\s+stimulation", r"re:omm?aya\w*",
                     r"re:neuro[\s-]?navigation"],
    "obstetrics_maternity": [r"re:mother\s*(and|&)?\s*(child|baby|newborn)\w*", r"re:labou?r\s+wards?",
                             r"re:women('s)?\s+(wing|wards?)", r"re:perineal"],
    "orthopedic_surgery": [r"re:(knee|hip|joint|shoulder)\s+(replacement|reconstruction|preservation)\w*",
                           r"re:arthroplast\w*", r"re:sports\s+injur\w*", r"re:limb\s+lengthening",
                           r"re:deformity\s+correction", r"re:hand\s+surg\w*"],
}
# services kept on the old Confirmed rule (term gate off) because the term list would still
# demote > 30% of their Confirmed rows after the synonym pass
TERM_GATE_OFF = {"neurosurgery", "obstetrics_maternity"}  # 41.6% and 33.7% after the synonym pass

# Dedicated-facility terms (wave 1 fix): a sentence naming one of these counts as "detailed"
# (explicit) even without a count. Hand-written for the 8 hand-checked services; every other
# service uses its term list plus a facility noun (FACILITY_NOUN_RE in build_facility_service.py).
# A bare service name or a department name is not detailed.
DEDICATED = {
    "dialysis": [r"re:(ha?emo[\s-]?)?dialy\w*\s+(unit|units|cent(re|er)s?|machines?|stations?|wards?|rooms?|beds?|chairs?|facilit(y|ies)|wing)",
                 r"re:(machines?|units?|stations?)\s+for\s+(ha?emo)?dialy\w*", "crrt",
                 # dialysis-specific infrastructure: RO / water treatment plant, isolation (HBV/HCV) machines or rooms
                 r"re:dialy\w*\s+(water|ro\s+plant|reverse\s+osmosis)",
                 r"re:isolat\w*\s+(\w+\s+){0,8}?(ha?emo)?dialy\w*"],
    "caesarean_section": [r"re:(obstetric\w*|maternity|labou?r|lscs|ca?esa?r(e|i|ea|ia)n\w*)\s+(section\s+)?(ot|ots|operation\s+theat\w*|operating\s+theat\w*|theat\w*|suites?)"],
    "nicu": [r"re:n\.?i\.?c\.?u\.?s?", r"re:neo[\s-]?natal\s+(intensive\s+care\s+units?|icu)",
             r"re:new[\s-]?born\s+(intensive\s+care\s+units?|icu)", r"re:level[\s-]*(ii|iii|2|3)\s+(neonatal|nicu|newborn)\w*"],
    "cardiac_surgery": [r"re:(cardiac|heart|cardio[\s-]?thoracic|cardiothoracic|ctvs)\s+(surg\w*\s+)?(ot|ots|operation\s+theat\w*|operating\s+theat\w*|theat\w*|icu|units?|suites?)",
                        r"re:heart[\s-]+lung\s+machines?"],
    "mri": [r"re:mri\s+(scanners?|machines?|units?|suites?|cent(re|er)s?|facilit(y|ies))", "tesla",
            r"re:\d(\.\d)?\s?t(?![a-z])", r"re:magnetic\s+resonance\s+(scanners?|machines?|units?)"],
    "burn_care": [r"re:burns?\s+(units?|wards?|icu|cent(re|er)s?|care\s+units?|beds?)"],
    "icu_critical_care": [r"re:i\.?c\.?u\.?s?", "iccu", "ccu", "micu", "sicu", "cticu",
                          r"re:intensive\s+care\s+units?", r"re:critical\s+care\s+units?"],
    "trauma_emergency": [r"re:trauma\s+(cent(re|er)s?|units?|wards?|icu|bays?|theat\w*)",
                         r"re:emergency\s+(department|room|ward|unit)s?",
                         r"re:casualty\s+(wards?|units?|department|block)",
                         r"re:accident\s+(and|&)\s+emergency\s+(department|unit)s?"],
}


def dedicated_regex(service: str) -> str:
    """Combined whole-word regex of a hand-checked service's dedicated-facility terms; '' otherwise."""
    import re as _re
    parts = [t[3:] if t.startswith("re:") else r"[\s-]+".join(_re.escape(w) for w in t.split())
             for t in DEDICATED.get(service, [])]
    return (r"(?i)(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])") if parts else ""


def build_terms():
    rows = []
    for sv in SERVICES:
        for src, lst in (("hand" if sv in HAND_CHECKED else "generated", TERMS[sv]),
                         ("synonym_pass", SYNONYM_PASS.get(sv, []))):
            for t in lst:
                is_re = t.startswith("re:")
                rows.append((sv, t[3:] if is_re else t, is_re, sv in HAND_CHECKED, src))
    return rows


def term_regex(service: str) -> str:
    """Combined case-insensitive whole-word Java regex for a service; '' if no terms."""
    parts = []
    for sv, t, is_re, _, _ in build_terms():
        if sv != service:
            continue
        if is_re:
            parts.append(t)
        else:
            import re as _re
            parts.append(r"[\s-]+".join(_re.escape(w) for w in t.split()))
    if not parts:
        return ""
    return r"(?i)(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])"


def build_fit():
    rows = []
    for ft in FACILITY_TYPES:
        s = TYPE_SPEC[ft]
        for sv in SERVICES:
            fit, note = s["default"], f"type default ({s['why']})"
            for lvl in ("expected", "plausible", "unexpected"):
                if sv in s[lvl]:
                    fit, note = lvl, f"listed {lvl} for {ft}"
            if ft not in NON_CARE and fit == "unexpected":
                if sv in ("outpatient_opd", "laboratory_pathology", "other_clinical"):
                    fit, note = "plausible", f"global floor: {sv} plausible wherever care is given"
                elif sv == "xray" and ft not in XRAY_NOT_FLOOR:
                    fit, note = "plausible", "global floor: xray plausible wherever care is given"
            if (sv, ft) in EXCEPTIONS:
                fit, why = EXCEPTIONS[(sv, ft)]
                note = f"exception: {why}"
            rows.append((sv, ft, fit, note))
    return rows


def build_map():
    rows = []
    for sv in SERVICES:
        n0 = len(rows)
        for v, st, note in SPEC[sv]:
            rows.append((sv, "specialty", v, STRENGTH[st], note or DEF_NOTE[st]))
        for v, st, note in IMPLIED[sv]:
            rows.append((sv, "implied_by_service", v, STRENGTH[st],
                         note or ("evidence for that service makes this one likely" if st == "S"
                                  else "evidence for that service makes this one possible")))
        if len(rows) == n0:
            rows.append((sv, "specialty", None, None,
                         "catch-all label: no specialty or service backs it specifically"))
    return rows


def lit(x):
    return "NULL" if x is None else "'" + str(x).replace("\\", "\\\\").replace("'", "\\'") + "'"


def main():
    assert set(SPEC) == ALL and set(IMPLIED) == ALL and set(TYPE_SPEC) == set(FACILITY_TYPES)
    for sv in SERVICES:
        for v, _, _ in IMPLIED[sv]:
            assert v in ALL and v != sv, (sv, v)
    for (sv, ft) in EXCEPTIONS:
        assert sv in ALL and ft in FACILITY_TYPES
    for s in TYPE_SPEC.values():
        for lvl in ("expected", "plausible", "unexpected"):
            assert s[lvl] <= ALL, s[lvl] - ALL

    tok = json.loads(subprocess.check_output(["databricks", "auth", "token", "-p", "datathon"]))["access_token"]
    con = sql.connect(server_hostname="dbc-70851148-db1d.cloud.databricks.com",
                      http_path="/sql/1.0/warehouses/8ea2282aca435351", access_token=tok)
    cur = con.cursor()
    cur.execute("""select s, count(distinct unique_id) from workspace.vf.facilities_clean
                   lateral view explode(specialties) t as s where not is_shifted group by s""")
    counts = dict(cur.fetchall())
    map_rows = build_map()
    bad = sorted({r[2] for r in map_rows if r[1] == "specialty" and r[2] is not None
                  and counts.get(r[2], 0) < MIN_FACILITIES})
    assert not bad, f"specialty values below {MIN_FACILITIES} facilities: {bad}"
    fit_rows = build_fit()
    assert len(fit_rows) == len(SERVICES) * len(FACILITY_TYPES) == 60 * 26

    cur.execute(f"""create or replace table workspace.vf.service_department_map (
        service string comment 'Service label (one of the 60 labels in scripts/build_lookups.py SERVICES: 49 from pa_single_v1 + 11 from pa_single_v2)',
        link_type string comment 'specialty = value is a facilities_clean.specialties term; implied_by_service = value is another service label whose evidence implies this service is possible',
        value string comment 'Specialty term (exact facilities_clean.specialties value, in >= {MIN_FACILITIES} non-shifted facilities) or a service label; NULL only for other_clinical and ayush_traditional_medicine',
        strength string comment 'strong = the service''s own department/subspecialty or a near-certain implication; supporting = related, raises likelihood only',
        note string comment 'Why this link exists or its caveat')
      comment 'Hand-written: which specialties and which other services back each of the 60 service labels (49 + 11 added with prompt pa_single_v2). Department-only specialties (internalMedicine, familyMedicine, generalMedicine, preventiveMedicine, anesthesia) are never strong. Source and rebuild: scripts/build_lookups.py'""")
    cur.execute("insert into workspace.vf.service_department_map values " +
                ",".join("(" + ",".join(lit(x) for x in r) + ")" for r in map_rows))
    cur.execute("""create or replace table workspace.vf.service_type_fit (
        service string comment 'Service label (one of the 60 labels in scripts/build_lookups.py SERVICES: 49 from pa_single_v1 + 11 from pa_single_v2)',
        facility_type string comment 'facility_type value from workspace.vf.facility_type (26 values)',
        fit string comment 'expected | plausible | unexpected: how normal it is for this facility type to offer this service',
        note string comment 'Which rule decided the fit: type default, listed for type, global floor, or exception with reason')
      comment 'Hand-written: 60 services x 26 facility types = 1,560 rows, one fit per pair. Method: type default -> per-type expected/plausible/unexpected lists -> global floors (outpatient_opd, laboratory_pathology, other_clinical, xray at least plausible in care-giving types) -> explicit exceptions. Source and rebuild: scripts/build_lookups.py'""")
    cur.execute("insert into workspace.vf.service_type_fit values " +
                ",".join("(" + ",".join(lit(x) for x in r) + ")" for r in fit_rows))
    assert set(TERMS) == ALL, ALL ^ set(TERMS)
    term_rows = build_terms()
    cur.execute("""create or replace table workspace.vf.service_terms (
        service string comment 'Service label (60 labels)',
        term string comment 'Word/phrase that names the service; regex when is_regex (Java, matched case-insensitive and whole-word on the original sentence)',
        is_regex boolean comment 'true = term is a regex; false = plain phrase (spaces match space or hyphen)',
        hand_checked boolean comment 'true for the 8 headline services reviewed by hand for synonyms and false friends',
        source string comment 'hand | generated (from label, readable name, obvious synonyms) | synonym_pass (added after reading demoted quotes)')
      comment 'Hand-written term lists per service (wave 1). scripts/build_facility_service.py requires >= 1 non-demoted explicit/stated claim sentence matching the list for Confirmed (term gate), except services in TERM_GATE_OFF (see workspace.vf.service_term_gate). Source and rebuild: scripts/build_lookups.py'""")
    cur.execute("insert into workspace.vf.service_terms values " +
                ",".join("(" + ",".join("true" if x is True else "false" if x is False else lit(x) for x in r) + ")"
                         for r in term_rows))
    for t in ("service_department_map", "service_type_fit", "service_terms"):
        cur.execute(f"select count(*), count(distinct service) from workspace.vf.{t}")
        print(t, cur.fetchone())
    cur.execute("select fit, count(*) from workspace.vf.service_type_fit group by 1 order by 1")
    print(cur.fetchall())
    cur.close()
    con.close()


if __name__ == "__main__":
    main()
