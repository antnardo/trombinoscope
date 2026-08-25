# Exemples

Trois exemples, du plus court au plus complet.

## 01 — minimal

[`01_minimal.py`](01_minimal.py) — trois lignes utiles : un dossier de photos,
une liste, un PDF.

```bash
uv run python examples/01_minimal.py photos/ classe.csv
```

## 02 — tour des options

[`02_options.py`](02_options.py) — six sections commentées et indépendantes, qui
écrivent chacune leurs PDF pour qu'on puisse comparer :

1. réglages par défaut ;
2. **cadrage** — `face_ratio`, `face_y`, redressement de la ligne des yeux ;
3. **couleur** — méthode de balance des blancs, intensité, harmonisation de lot
   contre correction photo par photo ;
4. **mise en page** — dispositions d'annotations, paysage, version sobre ;
5. **diagnostic** — absents, choix du visage, lecture du `BuildReport` ;
6. **briques séparées** — recadrer sans PDF, brancher son propre détecteur,
   harmoniser un lot d'images quelconques, paginer sans ReportLab.

```bash
uv run python scripts/fetch_samples.py     # portraits d'exemple, une seule fois
uv run python examples/02_options.py --sortie /tmp/demo
```

## 03 — cas réel : base SQLite

[`03_sqlite_prepa.py`](03_sqlite_prepa.py) — le cas dont ce paquet est issu : la
liste vient d'une base SQLite de classe préparatoire, la mise en page reproduit
celle utilisée depuis 2020 (sept colonnes, options dans la gouttière gauche,
étoile de cinq-demi à cheval sur le coin, logo en haut à droite).

Il montre surtout comment traduire un **schéma métier** vers le modèle générique
du paquet, avec des alias SQL et sans toucher à la base :

```sql
SELECT nom, prenom, cube AS badge,
       option || ';' || LV1 || ';' || LV2 AS tags,
       'Gr' || groupe || ';Tr' || groupecolle AS groupes
FROM eleves ORDER BY nom
```

```bash
export TROMBI_RACINE=~/mes-classes/MP TROMBI_CLASSE=MP2 TROMBI_ANNEE=2025
uv run python examples/03_sqlite_prepa.py
```

## Données d'exemple

[`classe-exemple.csv`](classe-exemple.csv) contient huit personnes, dans l'ordre
des portraits que `scripts/fetch_samples.py` télécharge. Ces portraits sont sous
licence libre et ne sont pas versionnés — voir [CREDITS.md](../CREDITS.md).
