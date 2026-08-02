#!/usr/bin/env python3
"""
batch_convert.py — Convertit un lot de GeoTIFF (cartes de parcours) en
images web (PNG) + un catalog.json prêt à déposer dans le dépôt GitHub
de la PWA Route Bleue.

UTILISATION
-----------
1. Installer les dépendances (une seule fois) :
       pip install rasterio pillow

2. Remplir routes.csv (voir routes_exemple.csv fourni à côté) avec une
   ligne par carte. Colonnes attendues :

       tif_path   -> chemin vers le fichier .tif sur ton ordi
       id         -> identifiant unique et court, sans espace/accent
                      (ex: lachute-1, riviere-rouge-secteurA)
       region     -> région touristique (ex: Laurentides)
       river      -> rivière (ex: Rivière du Nord)
       name       -> nom du parcours affiché dans l'appli
       km         -> longueur en km (nombre)
       niveau     -> Débutant / Intermédiaire / Avancé / Expédition

3. Lancer :
       python batch_convert.py routes.csv --outdir sortie

4. Le dossier "sortie/" va contenir :
       - une image map-<id>.png par ligne du CSV
       - un catalog.json combinant tout

   Glisse le contenu de "sortie/" dans ton dépôt GitHub, à la racine,
   par-dessus les fichiers existants. catalog.json remplace celui
   d'avant (ou le crée s'il n'existait pas encore).

Ce script ne modifie jamais tes fichiers .tif originaux — il les lit
seulement.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    import rasterio
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print("Dépendance manquante:", e)
    print("Installe-les avec:  pip install rasterio pillow numpy")
    sys.exit(1)

# Couleurs de la charte Route Bleue (voir carte-route-bleue_14052026.html)
BRAND = (0, 37, 105)        # #002569
MIST = (242, 248, 252)      # #F2F8FC

MAX_SIDE = 1600  # taille max en pixels du plus long côté, pour rester léger


def convert_one(tif_path: Path, label: str):
    """Lit un GeoTIFF, retourne (image, geo_dict). Pas de bandeau de titre :
    l'image est juste la carte — le nom du parcours s'affiche déjà dans l'appli."""
    with rasterio.open(tif_path) as src:
        arr = src.read()
        w, h = src.width, src.height
        t = src.transform
        crs_proj4 = src.crs.to_proj4()

        if src.count >= 3:
            img_arr = np.transpose(arr[:3], (1, 2, 0))
            img = Image.fromarray(img_arr, mode="RGB")
        else:
            img = Image.fromarray(arr[0]).convert("RGB")

    scale = min(1.0, MAX_SIDE / max(w, h))
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    canvas = img.resize((new_w, new_h), Image.LANCZOS)

    geo = {
        "crs_proj4": crs_proj4,
        "transform": [t.a, t.b, t.c, t.d, t.e, t.f],
        "orig_width": w,
        "orig_height": h,
        "content_height": new_h,
        "header_height": 0,
        "total_width": new_w,
        "total_height": new_h,
    }
    return canvas, geo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", help="Chemin vers routes.csv")
    ap.add_argument("--outdir", default="sortie", help="Dossier de sortie (défaut: sortie)")
    args = ap.parse_args()

    csv_path = Path(args.csv_path)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    regions = {}   # region -> { river -> [routes] }
    geo_all = {}
    ok, fail = 0, 0

    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"tif_path", "id", "region", "river", "name", "km", "niveau"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print(f"Colonnes manquantes dans le CSV: {', '.join(sorted(missing))}")
            sys.exit(1)

        for row in reader:
            tif_path = Path(row["tif_path"].strip())
            route_id = row["id"].strip()
            if not tif_path.exists():
                print(f"⚠ Fichier introuvable, ligne ignorée: {tif_path}")
                fail += 1
                continue
            try:
                label = f"{row['river'].strip()} — {row['name'].strip()}"
                canvas, geo = convert_one(tif_path, label)
                out_png = outdir / f"map-{route_id}.png"
                canvas.save(out_png)
                geo_all[route_id] = geo

                region = row["region"].strip()
                river = row["river"].strip()
                regions.setdefault(region, {}).setdefault(river, []).append({
                    "id": route_id,
                    "name": row["name"].strip(),
                    "km": float(row["km"]) if row["km"].strip() else None,
                    "niveau": row["niveau"].strip(),
                    "duree": row["duree"].strip() if "duree" in row and row["duree"].strip() else None,
                })
                print(f"✓ {route_id} -> {out_png.name}")
                ok += 1
            except Exception as e:
                print(f"✗ Erreur sur {tif_path}: {e}")
                fail += 1

    # Reformate regions/rivers en la structure attendue par l'appli
    catalog_regions = []
    for region, rivers in regions.items():
        catalog_regions.append({
            "region": region,
            "rivers": [{"river": river, "routes": routes} for river, routes in rivers.items()],
        })

    catalog = {"regions": catalog_regions, "geo": geo_all}
    with (outdir / "catalog.json").open("w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé — {ok} carte(s) convertie(s), {fail} ignorée(s)/en erreur.")
    print(f"Contenu prêt dans: {outdir.resolve()}")
    print("Glisse tout le contenu de ce dossier dans ton dépôt GitHub (racine).")


if __name__ == "__main__":
    main()
