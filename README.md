# SDOC Hackathon - Averis x Monash 2026

Email triage and shipping-document verification. Classifies inbox messages,
then compares a Shipping Instruction against a draft Bill of Lading across
seven fields, reporting mismatches or escalating what it cannot decide.

## Setup

    python -m venv .venv
    .venv/Scripts/activate
    pip install -r requirements.txt

## Dataset

Supplied by the organizers and not redistributed here. Extract the participant
bundle so that inbox/ and attachments/ sit in the project root.

## Run

    python run.py

Writes submission.json.

## Scoring (development only)

Uses the organizers evaluator, kept outside this repo in tools/ with the
reference answers in secrets/. Neither is redistributed.

Baseline for a do-nothing submission: 0.0124
