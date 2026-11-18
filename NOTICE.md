# Provenance and third-party notices

FastReads Taso adapts the supplied Python server, standalone NiiVue viewer, sidebar/display controls, and platform launcher paths from the original `fastreads` project. At preflight, all six seeded runtime files matched the corresponding files in `../fastreads` byte for byte. That sibling is a development reference only; this application never imports or reads it at runtime. No upstream application license was supplied with the seed; this notice records provenance and does not grant new rights to that application code. Confirm its redistribution permission before distributing the application beyond the authorized project.

The optional read-only `fastreads-jcb` reference informed atomic-write, allowlist and readiness design. Its frontend, report code, dependencies and shipment implementation were not imported.

`niivue.umd.js` is the original, unmodified locally bundled NiiVue renderer (internal version string `0.68.1`). Its SHA-256 is:

```
eb805352d555858708b5eb52a4b65f8eea37ddb7bc868506ac992126584b7784
```

NiiVue is copyright (c) 2021, Niivue, under the BSD 2-Clause License. Retain [the full license](licenses/NiiVue-LICENSE.txt) with the bundle and with any code-only distribution. The license was obtained from the [official NiiVue repository](https://github.com/niivue/niivue/blob/main/LICENSE). No runtime internet access is needed. Any additional third-party notices embedded in the supplied bundle remain intact.
