# Sienna Grabber

This is a fork of https://github.com/major/yotagrabber with very specific
parameters like a MODEL, a ZIPCODE and DISTANCE.

## Installation

Install [poetry](https://python-poetry.org/docs/).

Install dependencies:

```bash
poetry install --only main
```

Install Playwright browsers:

```bash
poetry run playwright install firefox
```

Run script:

```bash
poetry run update_vehicles
```