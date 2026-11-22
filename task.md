CMU Datathon - Fall 2026

Presented by

     


Your challenge this weekend: find the right care


A patient needs a specific kind of care. Where should they go, and why should they trust that answer?


A community health worker in rural Bihar has a patient who needs dialysis. An NGO coordinator in Maharashtra needs a hospital that can handle a high-risk delivery. A district planner wants to know where to send trauma cases from a highway accident hotspot. They're all asking the same thing: where is the best place to get this service, from here?


The Virtue Foundation dataset lists about 10,000 healthcare facilities across India. But a facility saying it offers a service isn't the same as actually offering it. Some records merge two hospitals, some have contradictory locations, and some list services with almost nothing to back them up. A confident wrong answer can cost a patient hours they don't have.


Your mission: build something that takes two inputs:

a service: e.g. dialysis, emergency C-section, NICU, cardiac surgery, MRI, burn care
a location: e.g. a city, district, PIN code or set of coordinates
and returns the best facility option(s), with a clear, evidence-based explanation of why each one was chosen.


It can be any format: an app, a dashboard, a Genie space, a notebook, an agent, or a mix. Consider carefully the best way of communicating with the audience that you’d expect to use this service.


The one rule: show your reasoning. Every team must be able to answer two questions about every recommendation their build makes:


WHY this facility? What evidence says this facility exists, offers this service, and is the best choice for this location?
HOW did you decide? What logic, scoring, model or rules turned 10,000 records into this answer? What did you weigh, and what did you trade off?

If your build can't explain itself, it doesn't meet the challenge requirements, however good it looks.


Your submission must:

Run on Databricks Free Edition.
Use the provided facility dataset.
Support a clear non-technical user workflow.
Cite the underlying facility text for any important claim, recommendation, score, or ranking.
Communicate uncertainty instead of presenting weak evidence as fact.

About the dataset

Every day, NGOs and healthcare planners have to answer questions like "Where can a patient get dialysis near Jaipur?" or "Which hospital near Lucknow can handle an emergency C-section?". The information they need exists, but it's spread across thousands of websites, directories and listings, and much of it is incomplete, out of date or contradictory.


The Virtue Foundation is a nonprofit that works to improve access to healthcare around the world. It has put together a dataset of about 10,000 healthcare facilities across India, with 51 attributes per facility. Each record includes:


Identity and location: facility name, state, city, postcode, latitude and longitude
What the facility says it offers: specialties, capabilities, procedures and equipment
Scale and history: number of doctors, bed capacity, year established
Evidence: a free-text description and the source URLs the record was pulled from

What makes this dataset interesting (and hard) is that most of it was extracted from unstructured web text, so treat every field as a claim to verify, not ground truth. Coverage is uneven:


Field

Coverage

Description

100%

Capability

99.7%

Procedure

92.5%

Equipment

77.0%

Year established

47.8%

Number of doctors

36.4%

Capacity

25.2%


Some records merge information from more than one facility, or list locations and capabilities that contradict each other. Working out how much to trust the data is part of the challenge.


Accessing the dataset

To access the dataset and complete the challenge, you’ll need to sign up for Databricks Free Edition.


Click here to sign up for Databricks Free Edition


Once you’re signed up, you can access the dataset through the Databricks Marketplace.


Click here to open the dataset on the Databricks Marketplace


