# empire-rankings

Website allowing to consult the rankings for the different events of the game [Goodgame Empire](https://empire.goodgamestudios.com) using the [Goodgame Empire API](https://github.com/danadum/empire-api).

The live version is available [here](https://danadum.github.io/empire-rankings).

## Contributors
- [danadum](https://githbub.com/danadum) - original project creator
- [Debjeet Das](https://github.com/dasdebjeet) - created new CSS design
- [Fear](https://github.com/FearMyShotz) - updated events, implemented light and dark designs
## Automatic Gacha ranking selection

The repository synchronizes the current Gacha ranking every six hours through `.github/workflows/sync-gacha.yml`. The workflow can also be started manually through GitHub Actions.

`scripts/update_gacha.py` downloads the DLL preload referenced by the official Goodgame Empire browser client and extracts both `HighscoreConst` ranking IDs and `EventConst` event IDs. The parser accepts minified official bundles and the readable exported symbols published by `gge-services/client-source`. The latter are used as an independent comparison, not as a prerequisite for updating the ranking.

All mapped Gacha rankings are probed through the existing `empire-api.fly.dev` bridge using the `hgh` command. A valid reply must contain the requested ranking type, a nonempty ranking list and a positive last rank. HTTP 400 is treated as an unavailable leaderboard. The permanent decoration Gacha is used only when no seasonal Gacha is confirmed. Simultaneously available seasonal Gachas, inconsistent client IDs or unexpected API failures abort the update without overwriting the last known selection.

The workflow updates `events.json` and `active-gacha.json` only when the data actually changes. The default reference server is `EmpireEx_2` (Germany 1). Other servers are checked in the browser when selected. The page automatically switches to a newly confirmed active Gacha, but preserves a user's manual event choice when that active Gacha has not changed.

To test locally:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/update_gacha.py
node --check main.js
```

The workflow requires GitHub Actions write permission to commit generated data to `main`; branch protection rules must permit these automated commits. A failed sync keeps the previous published files and causes a visible failed workflow run.
