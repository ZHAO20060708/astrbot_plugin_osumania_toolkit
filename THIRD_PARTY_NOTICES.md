# Third-party notices

## Sunny Rework compatibility implementation

The files under `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/rework/sunny-rework/` are
vendored from [ZHAO20060708/sunny-rework-js](https://github.com/ZHAO20060708/sunny-rework-js).
They target Sunny Rework compatibility revision `2025-04-15` and are
distributed under that project's MIT license.

Source repository: <https://github.com/ZHAO20060708/sunny-rework-js>

The surrounding adapter remains project code and preserves this application's
existing text-based estimator API.

## WenYuan Rounded SC font

- Files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/styles/fonts/WenYuanRoundedSC-Regular.otf` (400) and `WenYuanRoundedSC-Heavy.otf` (900)
- Source: <https://github.com/takushun-wu/WenYuanFonts>
- License: SIL Open Font License 1.1
- License text: `LICENSES/WenYuanFonts-OFL.txt`

The font is used as the replacement for the previously bundled 975 Yuan files.

## Outfit and Space Grotesk fonts

- Outfit files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/styles/fonts/Outfit-*.woff2`
- Space Grotesk files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/styles/fonts/SpaceGrotesk-*.woff2`
- License: SIL Open Font License 1.1
- License texts: `LICENSES/Outfit-OFL.txt`, `LICENSES/SpaceGrotesk-OFL.txt`

Both font families are actively referenced by the application's CSS and are
therefore intentionally retained.

## Daniel algorithm

- Files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/rework/danielAlgorithm.js` and
  `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/estimator/danielEstimator.js`
- Source: <https://github.com/TheBagelOfMan/Daniel>
- License: MIT
- License text: `LICENSES/daniel-MIT.txt`

## YAVSRG Prelude calculator code

- Files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/interlude/`
- Source: <https://github.com/YAVSRG/YAVSRG/tree/master/prelude>
- License: MIT
- License text: `LICENSES/yavsrc-prelude-MIT.txt`

The local JavaScript is based on the calculator code from YAVSRG's `prelude`
directory. It is not copied from the GPLv3 `interlude` game-client directory.

## Etterna MinaCalc

- Files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/ett/versions/`
- Source: <https://github.com/etternagame/etterna>
- License: MIT
- License text: `LICENSES/etterna-MIT.txt`

This notice covers the bundled MinaCalc JavaScript loaders and WebAssembly
payloads, including the unofficial 0.68.0 build currently shipped here.

## ONNX Runtime Web

- Files: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/estimator/companella/ort/`
- Source: <https://github.com/microsoft/onnxruntime>
- License: MIT
- License text: `LICENSES/onnxruntime-MIT.txt`

## Companella adapter and model

- Adapter: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/estimator/companellaEstimator.js`
- Model: `osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/estimator/companella/dan_model.onnx`
- Source: <https://github.com/Leinadix/companella>
- License: MIT, according to the upstream repository root `LICENSE`
- License text: `LICENSES/companella-MIT-and-notices.txt`

The model is committed in the upstream repository and no separate model
license or exception is present. The upstream README also describes the
project as “for personal use”, which conflicts with the root MIT license. Treat
the root MIT license as the current repository-level grant, but obtain upstream
author confirmation before commercial redistribution of the model.
