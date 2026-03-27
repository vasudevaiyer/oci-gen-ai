# OCI Multimodal Extract Compare

Small Streamlit app for uploading a PDF or image, sending it to multiple OCI-hosted multimodal GenAI models, and viewing the extracted fields side by side.

## Included presets

- `cohere.command-a-vision`
- `google.gemini-2.5-flash`
- `meta.llama-3.2-90b-vision-instruct`

## What the app does

- Uploads a PDF or image from the browser.
- Converts PDFs into rendered page images so the same input path works across all three model families.
- Lets you select one or more preset multimodal models in the UI.
- Sends the images plus an extraction prompt to OCI Generative AI.
- Displays:
  - a comparison summary across all selected models
  - extracted fields per model as `field -> value`
  - parsed JSON if the model returned valid JSON
  - raw text from each model
  - full raw OCI response payload per model
  - original PDF/image preview plus rendered page previews

## Run

Use the requested Python environment:

```bash
source /u01/venv/bin/activate
streamlit run /u01/scripts/oci_samples/multi_modal_extract/app.py
```

## OCI configuration

The UI defaults to:

- OCI config path: `/home/opc/.oci/config`
- OCI profile: `DEFAULT`

You can also create a local `.env` from `.env.example` if you prefer not to rely only on the OCI config file.

The app reads these values from the selected profile when present:

- `region`
- `OCI_GENAI_ENDPOINT`
- `OCI_COMPARTMENT_OCID`

If the config file does not contain those fields, you can enter the endpoint and compartment OCID directly in the sidebar.

## Notes

- PDF comparison is page-image based by design, which keeps input handling consistent across Cohere, Gemini, and Meta vision models.
- The app asks the model to return strict JSON, but some responses may still need prompt tuning.
- If your selected OCI region does not host a given model, the inference call will fail with a service error in the UI.
- This sample does not commit tenancy-specific OCIDs, endpoints beyond region defaults, or private key material. Keep your actual values in `/home/opc/.oci/config` or a local `.env` that is ignored by git.
