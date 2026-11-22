# Source display audit (read-only)

Logic audited: `source_list()` in `app/main.py`, imported directly. Data: `workspace.vf.facilities_clean`, non-shifted rows (9,989).
Sample: first 20 by `md5(concat('src_audit', unique_id))`.

## Population counts (what the card shows)

| Category | Facilities | Share |
|---|---|---|
| (a) Official website shown | 6,468 | 64.8% |
| (b) Name-matched source(s), no official | 586 | 5.9% |
| (c) Listings only | 2,406 | 24.1% |
| (d) Nothing at all | 529 | 5.3% (527 of them do have domains, all hidden) |

## Sample of 20

"Hidden" = every domain on the record not shown (incl. listing sites dropped by the 3-item cap). Flags: **HIDDEN-OWN** = hidden domain that is the facility's own; **SHOWN-NOT-OWN** = shown domain not belonging to it.

| # | Name | City | Shown | Hidden | Flag |
|---|---|---|---|---|---|
| 1 | Anupama Maternity & Nursing Home | Mumbai | healthfrog.in [L], justdial.com [L], mappls.com [L] | **anupamhospital.co.in** (official), facebook.com, medicineindia.org, practo.com | HIDDEN-OWN: official site, token "anupama" vs host "anupam" (spelling) |
| 2 | Pl Memorial Eye Clinic | Gurgaon | docindia.org [L] | **drsameerkaushal.com** (official), cometeyehospitals.com, facebook.com, indiamart.com, proptiger.com | HIDDEN-OWN: page title "PL Memorial Eye Clinic (Dr Sameer Kaushal)" (doctor-named site) |
| 3 | Oasis Fertility | Vijayawada | oasisfertility.com, justdial.com [L], medindia.net [L] | biospectrumindia.com, facebook.com, gynoveda.com, instagram.com, ivftips4u.com, practo.com, sulekha.com | ok |
| 4 | Apple Hospital | Surat | applehospitalsurat.com, grotal.com [L], medindia.net [L] | indiamart.com | ok |
| 5 | SAI Spandan Hospital | Pune | bajajfinservhealth.in [L] | facebook.com, magicpin.in, newindia.co.in | ok |
| 6 | Chandigarh Clinical Laboratories | Chandigarh | justdial.com [L], mappls.com [L], medifee.com [L] | **ccllab.in** (official), bharatibiz.com, diagnosticcentres.in, facebook.com, in.indeed.com, indiamart.com, medindia.net, mediyaar.com, sulekha.com, tracxn.com | HIDDEN-OWN: official site, abbreviation CCL |
| 7 | New City Hospital | Bulandshahr | docindia.org [L], drlogy.com [L], justdial.com [L] | facebook.com, practo.com | ok |
| 8 | Prashamsa Hospital | Hyderabad | prashamsahospital.com, justdial.com [L], practo.com [L] | insurancedekho.com, policyx.com, starhealth.in | ok |
| 9 | Sdrc Laboratory | Thiruvananthapuram | justdial.com [L] | diagnosticcentres.in, facebook.com, magicpin.in | ok |
| 10 | Sg Imaging Diagnostiqs | Ghaziabad | justdial.com [L] | facebook.com, magicpin.in | ok |
| 11 | Kurumathur AryaVaidyasala & Nursing Home | Taliparamba | kurumathurayurveda.com | ayurvedam4you.com, facebook.com, matha.net, nmpb.nic.in | ok |
| 12 | Susrutha Institute of Ayurvedic Sciences and Panchakarma Hospital | Thiruvananthapuram | susruthaayurveda.com | facebook.com, instagram.com, keralatourism.org | ok |
| 13 | Chandra Laxmi Healthcare Multispeciality Hospital | Ghaziabad | chandralaxmihealthcare.com, docindia.org [L], hexahealth.com [L] | numedhospital.com, samyakeyecare.com, labs.lalpathlabs.com, two *.wheree.com pages of other hospitals, justdial/practo/lybrate/medindia + 9 more | ok (merged-record domains correctly hidden) |
| 14 | Gloss Dental | Gurgaon | glossdental.co.in, glossdental.setmore.com, docindia.org [L] | facebook.com | ok (setmore = its booking page) |
| 15 | Vijaya Fertility Clinic IVF & Endoscopy Centre, Kochi | Cochin | vijaya-ivf.com | doctorskerala.com, ernakulam.nic.in, hospitalskerala.in, ivf-worldwide.com, proptiger.com | ok |
| 16 | Sunayan Eye Hospital | Bareilly | sunayaneyehospital.in, bajajfinservhealth.in [L], justdial.com [L] | facebook.com, hospitaltraders.com, iffcotokio.co.in, in.near-place.com, insurancedekho.com, mapcarta.com, medindia.net, seminarsonly.com | ok |
| 17 | APS Nursing Home and IVF Centre | Pune | aps-nursing-home.business.site, bajajfinservhealth.in [L] | facebook.com | ok |
| 18 | Parvathy Medical Centre | Ooty | bajajfinservhealth.in [L], justdial.com [L], onefivenine.com [L] | facebook.com | ok |
| 19 | Regain Dental Clinic | Meerut | justdial.com [L], mappls.com [L] | chotu.com, facebook.com, magicpin.in | ok |
| 20 | Knee & Ortho Clinic | Chennai | kneecareindia.in, chennaikneeclinic.in, kneeworld.in | facebook.com, robotickneesurgery.in | uncertain: matched only on generic "knee". kneecareindia.in and kneeworld.in are both Dr Raj Kanna's sites (likely own); chennaikneeclinic.in unverified (empty title) |

[L] = tagged "listing".

## Errors

- **Hidden-but-own: 3/20** (#1 spelling variant, #2 doctor-named official site, #6 abbreviation). All three are the record's own `official_domain`, so the card drops the facility's real website and shows "listings only".
- **Shown-but-not-own: 0/20 confirmed**, 1 at risk (#20, "knee"/"ortho" act as distinctive tokens even though they are generic, so any knee-clinic domain would match).

Page loads used: 7 (homepage titles / one body grep).

## Rerun after prefix and acronym matching (2026-11-22)

Change to `source_list()` in `app/main.py`: a domain also counts as the facility's own when (a) its first label shares a prefix of at least 5 letters with a name token of at least 5 letters, covering all but at most the token's last letter ("anupama" vs "anupamhospital"), or (b) its first label starts with the name's initials, at least 3 letters (of/and/the skipped, city words counted: "ccl" in ccllab.in). "knee" and "ortho" are now generic name words. The official site is still not shown automatically. Same 20 records, same seed, same judging.

| # | Name | Shown now | Change vs first run |
|---|---|---|---|
| 1 | Anupama Maternity & Nursing Home | anupamhospital.co.in, healthfrog.in [L], justdial.com [L] | fixed: official site shown (prefix rule) |
| 2 | Pl Memorial Eye Clinic | docindia.org [L] | still HIDDEN-OWN (doctor-named site drsameerkaushal.com) |
| 3–5, 7–19 | (unchanged) | same as first run | no change |
| 6 | Chandigarh Clinical Laboratories | ccllab.in, justdial.com [L], mappls.com [L] | fixed: official site shown (initials rule) |
| 20 | Knee & Ortho Clinic | nothing ("Sources: listings only", no listing on record) | was at risk of SHOWN-NOT-OWN; now kneecareindia.in (official) and kneeworld.in are hidden, judged likely own in the first run |

- **Hidden-but-own: 2/20** (was 3/20): #2 confirmed; #20 likely own (both domains are Dr Raj Kanna's sites, judged in the first run), now hidden because "knee" is generic.
- **Shown-but-not-own: 0/20** (was 0 confirmed + 1 at risk). No page loads used for the rerun; judgements reuse the first run's.
