# Lookup tables: sample rows

Built by scripts/build_lookups.py. service_department_map 442 rows; service_type_fit 1,274 rows. Specialty cutoff: >= 20 non-shifted facilities (215 of the values qualify).

## service_department_map (service | link_type | value | strength | note)

- burn_care | specialty | plasticSurgery | supporting | related department; raises likelihood, does not prove the service
- burn_care | specialty | reconstructivePlasticSurgery | supporting | related department; raises likelihood, does not prove the service
- burn_care | specialty | underseaAndHyperbaricMedicine | supporting | related department; raises likelihood, does not prove the service
- burn_care | specialty | woundHealingAndDermatologicRegenerativeMedicine | supporting | related department; raises likelihood, does not prove the service
- burn_care | specialty | burnAndTraumaPlasticSurgery | strong | specialty is this service's own department or subspecialty
- burn_care | implied_by_service | icu_critical_care | supporting | evidence for that service makes this one possible
- burn_care | implied_by_service | trauma_emergency | supporting | evidence for that service makes this one possible
- caesarean_section | specialty | anesthesia | supporting | needed for C-section; department-only, over-assigned
- caesarean_section | specialty | anesthesiology | supporting | related department; raises likelihood, does not prove the service
- caesarean_section | specialty | gynecology | supporting | gynecology alone may exclude obstetrics
- caesarean_section | specialty | neonatologyPerinatalMedicine | supporting | related department; raises likelihood, does not prove the service
- caesarean_section | specialty | gynecologyAndObstetrics | strong | obstetrics department; C-section is core obstetric surgery
- caesarean_section | specialty | maternalFetalMedicineOrPerinatology | strong | specialty is this service's own department or subspecialty
- caesarean_section | specialty | obstetricsAndGynaecology | strong | obstetrics department; C-section is core obstetric surgery
- caesarean_section | specialty | obstetricsAndGynecology | strong | obstetrics department; C-section is core obstetric surgery
- caesarean_section | specialty | obstetricsAndMaternityCare | strong | obstetrics department; C-section is core obstetric surgery
- caesarean_section | implied_by_service | nicu | supporting | evidence for that service makes this one possible
- caesarean_section | implied_by_service | normal_delivery | supporting | evidence for that service makes this one possible
- caesarean_section | implied_by_service | high_risk_obstetrics | strong | evidence for that service makes this one likely
- caesarean_section | implied_by_service | obstetrics_maternity | strong | obstetric units perform C-sections
- cardiac_surgery | specialty | cardiology | supporting | cardiology is medical; does not imply surgery
- cardiac_surgery | specialty | pediatricCardiology | supporting | related department; raises likelihood, does not prove the service
- cardiac_surgery | specialty | vascularSurgery | supporting | related department; raises likelihood, does not prove the service
- cardiac_surgery | specialty | cardiacSurgery | strong | specialty is this service's own department or subspecialty
- cardiac_surgery | specialty | cardiothoracicSurgery | strong | specialty is this service's own department or subspecialty
- cardiac_surgery | implied_by_service | interventional_cardiology | supporting | evidence for that service makes this one possible
- dialysis | specialty | renalTransplantationUrology | supporting | related department; raises likelihood, does not prove the service
- dialysis | specialty | transplantSurgery | supporting | renal transplant programmes need dialysis
- dialysis | specialty | urology | supporting | related department; raises likelihood, does not prove the service
- dialysis | specialty | nephrology | strong | nephrology department usually runs haemodialysis; still a department, not proof of a unit
- dialysis | specialty | pediatricNephrology | strong | specialty is this service's own department or subspecialty
- dialysis | implied_by_service | icu_critical_care | supporting | ICUs often run CRRT / bedside dialysis
- dialysis | implied_by_service | transplant | supporting | renal transplant needs dialysis support
- dialysis | implied_by_service | nephrology_renal | strong | nephrology services usually include dialysis
- mri | specialty | cardiothoracicRadiology | supporting | radiology department does not prove this machine exists
- mri | specialty | diagnosticRadiology | supporting | radiology department does not prove this machine exists
- mri | specialty | interventionalRadiology | supporting | radiology department does not prove this machine exists
- mri | specialty | neuroradiology | supporting | radiology department does not prove this machine exists
- mri | specialty | pediatricRadiology | supporting | radiology department does not prove this machine exists
- mri | specialty | radiology | supporting | radiology department does not prove this machine exists
- mri | implied_by_service | neurosurgery | supporting | evidence for that service makes this one possible
- mri | implied_by_service | spine_surgery | supporting | evidence for that service makes this one possible
- mri | implied_by_service | stroke_care | supporting | evidence for that service makes this one possible
- nicu | specialty | maternalFetalMedicineOrPerinatology | supporting | related department; raises likelihood, does not prove the service
- nicu | specialty | pediatricCriticalCareMedicine | supporting | related department; raises likelihood, does not prove the service
- nicu | specialty | pediatrics | supporting | related department; raises likelihood, does not prove the service
- nicu | specialty | neonatologyPerinatalMedicine | strong | neonatology implies newborn care; NICU beds still need text evidence
- nicu | implied_by_service | high_risk_obstetrics | supporting | high-risk deliveries need newborn intensive care
- nicu | implied_by_service | picu | supporting | evidence for that service makes this one possible

## service_type_fit (per service, facility_types grouped by fit)

- burn_care | plausible | general_hospital_or_nursing_home, government_health_centre, medical_college_teaching_hospital, multispecialty_hospital, other_single_specialty, unknown
- burn_care | unexpected | ayush_alternative, cancer, cardiac, dental, diagnostic_imaging_lab, ent_hearing_speech, eye, gastro_liver, general_clinic_polyclinic, home_care_or_ambulance, ivf_fertility, kidney_urology, maternity_women_children, mental_health_deaddiction, neuro, not_a_care_facility, orthopedic_spine, pediatric, physiotherapy_rehab, skin_hair_cosmetic
- caesarean_section | expected | general_hospital_or_nursing_home, maternity_women_children, medical_college_teaching_hospital, multispecialty_hospital
- caesarean_section | plausible | government_health_centre, ivf_fertility, unknown
- caesarean_section | unexpected | ayush_alternative, cancer, cardiac, dental, diagnostic_imaging_lab, ent_hearing_speech, eye, gastro_liver, general_clinic_polyclinic, home_care_or_ambulance, kidney_urology, mental_health_deaddiction, neuro, not_a_care_facility, orthopedic_spine, other_single_specialty, pediatric, physiotherapy_rehab, skin_hair_cosmetic
- cardiac_surgery | expected | cardiac
- cardiac_surgery | plausible | general_hospital_or_nursing_home, medical_college_teaching_hospital, multispecialty_hospital, pediatric, unknown
- cardiac_surgery | unexpected | ayush_alternative, cancer, dental, diagnostic_imaging_lab, ent_hearing_speech, eye, gastro_liver, general_clinic_polyclinic, government_health_centre, home_care_or_ambulance, ivf_fertility, kidney_urology, maternity_women_children, mental_health_deaddiction, neuro, not_a_care_facility, orthopedic_spine, other_single_specialty, physiotherapy_rehab, skin_hair_cosmetic
- dialysis | expected | kidney_urology, medical_college_teaching_hospital, multispecialty_hospital
- dialysis | plausible | general_hospital_or_nursing_home, government_health_centre, home_care_or_ambulance, other_single_specialty, pediatric, unknown
- dialysis | unexpected | ayush_alternative, cancer, cardiac, dental, diagnostic_imaging_lab, ent_hearing_speech, eye, gastro_liver, general_clinic_polyclinic, ivf_fertility, maternity_women_children, mental_health_deaddiction, neuro, not_a_care_facility, orthopedic_spine, physiotherapy_rehab, skin_hair_cosmetic
- mri | expected | diagnostic_imaging_lab, medical_college_teaching_hospital, multispecialty_hospital, neuro
- mri | plausible | cancer, cardiac, gastro_liver, general_hospital_or_nursing_home, government_health_centre, orthopedic_spine, other_single_specialty, pediatric, unknown
- mri | unexpected | ayush_alternative, dental, ent_hearing_speech, eye, general_clinic_polyclinic, home_care_or_ambulance, ivf_fertility, kidney_urology, maternity_women_children, mental_health_deaddiction, not_a_care_facility, physiotherapy_rehab, skin_hair_cosmetic
- nicu | expected | maternity_women_children, medical_college_teaching_hospital, pediatric
- nicu | plausible | general_hospital_or_nursing_home, government_health_centre, ivf_fertility, multispecialty_hospital, unknown
- nicu | unexpected | ayush_alternative, cancer, cardiac, dental, diagnostic_imaging_lab, ent_hearing_speech, eye, gastro_liver, general_clinic_polyclinic, home_care_or_ambulance, kidney_urology, mental_health_deaddiction, neuro, not_a_care_facility, orthopedic_spine, other_single_specialty, physiotherapy_rehab, skin_hair_cosmetic

Exception notes:
- mri | government_health_centre | plausible | exception: district hospitals sometimes have MRI (often PPP)
- dialysis | general_clinic_polyclinic | unexpected | exception: standalone dialysis centres are typed kidney_urology
- burn_care | other_single_specialty | plausible | exception: burn centres have no own type and fall here
