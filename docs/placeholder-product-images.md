# Scoped product-pack replacement (awaiting dry-run approval)

## Scope and research

`placeholder_product_scope_audit.csv` is the sole target list: exactly 64 IDs.
The command pins its SHA-256 checksum, so an edited/expanded audit is rejected.
Keep the original file bytes when copying it to another environment.

`product_image_replacement_research.json` records exact-name search leads for
all 64 products. Search results are leads, not proof of product identity.
`product_image_replacement_sources.json` records the selected source pages,
candidate URLs, human match/visual checks, downloaded-image SHA-256, permission
provenance, and individual manual-review reasons. The user confirmed supplier/
brand authorization for reuse in this task on 2026-09-13. That authorization
does not override recipe, species, life-stage, size, or image-quality checks.

The management command intentionally does not fuzzy-match names or select the
first search result automatically. Research is reviewed in the manifest first;
the dry-run then validates the current catalogue and reviewed image bytes.

## Preview only

```text
python manage.py fix_placeholder_product_images --dry-run
```

Reads only the audited IDs using the normally configured database. PostgreSQL
reads are performed inside a read-only transaction. It verifies availability,
archive state, image reference, brand/name/category, and variant IDs/sizes.
Any drift is SKIPPED, never overwritten. It does not query a new global target
set. It does not upload or update any record.

Validated candidates require public HTTPS, HTTP 200, PNG/JPEG/WebP Content-Type,
matching decoded format, successful full decoding, no animation, bounded size
(15 MiB/25 megapixels), minimum 400px short edge/600px long edge, and an exact
match to the visually reviewed byte hash. 800px or larger is preferred; genuine
788px official Drools images are retained at native resolution, not upscaled.
Unreviewed images and any uncertain product identity remain MANUAL_REVIEW.

Outputs:

- `product_image_replacement_dry_run.csv`: READY / MANUAL_REVIEW / FAILED / SKIPPED.
- `product_image_replacement_report.csv`: requested final-status schema; dry-run
  READY entries are SKIPPED with an explicit 'not applied' note, not REPLACED.
- Existing reports are retained with a unique suffix before a new report is written.

## Future application — do not run before user approval

```text
python manage.py fix_placeholder_product_images
```

Only fully reviewed candidates can reach the apply branch. The command verifies
that Cloudinary remains the configured storage, locks each target row, and
rechecks the audited identity/image/variants immediately before upload.
It appends and fsyncs an intent record to
`product_image_replacement_backup.csv` BEFORE uploading. It uses the ImageField's
existing storage with a new `products/verified-pack-...` name and records that
stored name in a second fsynced backup row BEFORE changing the database.

The only database write is a conditional `Product.objects.filter(...).update(image=...)`.
No model save hooks or other fields are involved; external URLs, variants,
pricing, stock, orders and existing Cloudinary files are preserved. No delete API
is called. Re-running an applied row skips it because its old image no longer
matches. An individual error is recorded without stopping unrelated products.

The backup is append-only. An intent row has a blank new asset name; a subsequent
row names the uploaded asset. A crash/DB rollback may leave a retained uploaded
asset: never assume the backup alone proves a committed update. Check the
current Product.image and final report before any recovery. Rollback should
conditionally restore old_image only when the current image equals the recorded
new_cloudinary_image. Do not delete either asset. No rollback has been executed.

## Local QA and tests

- `scripts/inspect_pack_candidates.py`: public page/retailer metadata inspection;
  does not initialize Django or write product records.
- `scripts/preview_pack_candidates.py`: downloads candidates to the existing
  ignored `catalog_exports/placeholder_image_review/` directory and creates
  contact sheets for human QA. These thumbnails are not production assets.
- `store/test_placeholder_images.py`: isolated scope, dry-run, download rejection,
  drift, permission, byte-hash, backup, image-only update, upload failure and rerun tests.

No templates, styles, models, migrations, checkout, payments or inventory code
are changed by this feature. No production apply, commit or push is authorized yet.
