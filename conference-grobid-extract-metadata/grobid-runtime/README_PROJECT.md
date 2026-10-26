# GROBID Runtime for This Project

This directory is a filtered copy of the upstream GROBID source tree from
`/Users/liziyu/code/grobid/git`, keeping only the parts needed to run local
PDF-to-TEI extraction for this project.

## Kept

- `grobid-home/`
  - runtime config, native tools, models, lexicons
- `grobid-core/`
  - shared extraction core used by the service
- `grobid-service/`
  - REST service layer
- `gradle/`, `gradlew`, `build.gradle`, `settings.gradle`, `gradle.properties`
  - minimal build/run entrypoints
- `Readme.md`, `LICENSE`
  - upstream reference and license

## Intentionally Excluded

- `.git/`, `.github/`
- `doc/`
- `grobid-trainer/`
- `Dockerfile.*`
- editor and repo housekeeping files

These excluded parts are not required for normal metadata extraction.

## What This Runtime Is For

Use this directory when you need to:

- start a local GROBID service
- parse new PDFs into TEI XML
- keep the extraction stack inside this project

## Typical Next Step

From this directory, the usual service entrypoint is the Gradle service task
documented by upstream GROBID. Before first use, confirm Java is available and
then run the service from this filtered runtime instead of the full upstream
checkout.
