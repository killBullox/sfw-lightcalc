# sfw-lightcalc

Calcolo illuminotecnico dei locali in Python: dai file fotometrici IES e dalla pianta del locale
ricava il layout degli apparecchi, l'illuminamento sul piano di lavoro, l'uniformità, l'abbagliamento
UGR e le mappe isolux.

Estratto e reso indipendente dal motore di calcolo usato internamente da Synapsis FW per la
progettazione illuminotecnica.

## Cosa fa

| Passo | Modulo | Metodo |
|---|---|---|
| Lettura fotometrie | `ies.py` | file IES LM-63 (anche TILT=INCLUDE, simmetrie dei piani C), interpolazione bilineare I(γ, C), flusso per integrazione sull'angolo solido, estrazione da archivi ZIP |
| Geometria e griglia | `geometry.py` | poligoni anche non convessi (a L, a U), zona del compito con fascia perimetrale esclusa (UNI EN 12464-1), passo massimo della griglia p = 0,2 · 5^log10(d) |
| Layout | `geometry.py`, `room.py` | griglia regolare con passo dal rapporto interdistanza/altezza, poi apparecchi aggiunti sul punto più buio finché Em e U0 raggiungono il requisito |
| Calcolo | `direct.py` | componente diretta punto per punto (E = I·cos γ / r²) più stima delle interriflessioni con il metodo della sfera integratrice |
| Calcolo completo (facoltativo) | `radiance.py` | interriflessioni con [Radiance](https://www.radiance-online.org) (`oconv`, `rtrace`, `ies2rad`) se installato |
| Abbagliamento | `ugr.py` | UGR con il metodo tabellare CIE 117 e indice di posizione di Guth, direzione di vista peggiore |
| Regolazione | `room.py` | se Em supera il requisito di oltre il 15%, dimming al requisito più 5% |
| Mappe | `isolux.py` | curve isolux a falsi colori, isolinee, quote dei lati e simboli degli apparecchi (PNG) |
| Riga di comando | `cli.py` | `run`, `ies-info`, `extract` |

## Installazione

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"        # su Windows: .venv\Scripts\pip
```

Dipendenze: numpy, scipy, matplotlib. Radiance è facoltativo: se presente, indicare la cartella dei
programmi nella variabile d'ambiente `RADIANCE_BIN` oppure aggiungerla al PATH.

## Uso

```bash
python examples/make_example_ies.py                       # rigenera i file IES di esempio
python -m sfw_lightcalc ies-info examples/downlight_3000lm.ies
python -m sfw_lightcalc run examples/progetto_esempio.json --out risultati
python -m sfw_lightcalc run examples/progetto_esempio.json --out risultati --backend radiance
```

`run` scrive `risultati/risultati.json` e una mappa `isolux_<locale>.png` per ogni locale, e stampa:

```
locale                Em    Emin     U0    UGR  app.  esito
ufficio              525     456   0.87   16.2     6  conforme
sala_riunioni_L      520     425   0.82   17.2     5  conforme
corridoio            105      90   0.85   16.6     4  conforme
```

### Formato del progetto

```json
{"rooms": [{
  "id": "ufficio",
  "polygon": [[0, 0], [6, 0], [6, 4.5], [0, 4.5]],
  "height": 2.7, "workplane": 0.8,
  "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2},
  "em_target": 500, "u0_target": 0.6, "ugr_max": 19,
  "luminaire": {"ies": "downlight_3000lm.ies"}
}]}
```

Unità in metri e lux. Al posto del file IES si può indicare `{"flux_lm": 3000}`: si usa un
apparecchio lambertiano ideale con quel flusso.

### Da Python

```python
from sfw_lightcalc import design_room
from sfw_lightcalc.direct import DirectBackend

res = design_room(room_dict, DirectBackend(), base_dir="examples")
print(res.em, res.u0, res.ugr, res.n_luminaires)
```

## Test

```bash
python -m pytest
```

I test controllano tra l'altro la legge dell'inverso del quadrato e del coseno, il flusso integrato
dei file IES rispetto al valore nominale, le simmetrie dei piani C, la griglia della UNI EN 12464-1
e il flusso completo della riga di comando. Il test con Radiance viene saltato se il programma non è
installato.

## Limiti

- Il motore interno stima le interriflessioni come componente uniforme: per valori da relazione
  usare il motore Radiance.
- Le mappe isolux mostrano la zona del compito; la fascia perimetrale esclusa dal calcolo è
  riempita con il valore del punto più vicino.
- I file IES in `examples/` sono sintetici e non descrivono prodotti reali.

## Licenza

MIT, vedi [LICENSE](LICENSE).
