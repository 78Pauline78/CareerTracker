import pandas as pd
import numpy as np
import requests
from pyproj import Transformer

EARTH_RADIUS_KM = 6371.0

# ── Conversion Lambert-93 → WGS84 ─────────────────────────────────────────────
def lambert93_to_wgs84(df: pd.DataFrame,
                       col_x: str = 'coordonneeLambertAbscisseEtablissement',
                       col_y: str = 'coordonneeLambertOrdonneeEtablissement') -> pd.DataFrame:
    """
    Lambert-93 (EPSG:2154) : X = abscisse (Est ~600 000-700 000), Y = ordonnée (Nord ~6 000 000-7 000 000)
    always_xy=True → transformer.transform(X, Y) retourne (longitude, latitude)
    """
    transformer = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

    df[col_x] = pd.to_numeric(df[col_x], errors='coerce')
    df[col_y] = pd.to_numeric(df[col_y], errors='coerce')

    # Sanity check : X Lambert doit être ~100 000 – 1 300 000
    #                Y Lambert doit être ~6 000 000 – 7 200 000
    mask = (
        df[col_x].notna() & df[col_y].notna() &
        df[col_x].between(100_000, 1_300_000) &
        df[col_y].between(6_000_000, 7_200_000)
    )

    lons, lats = transformer.transform(
        df.loc[mask, col_x].values,
        df.loc[mask, col_y].values
    )

    df['latitude']  = np.nan
    df['longitude'] = np.nan
    df.loc[mask, 'longitude'] = lons   # X Lambert → longitude
    df.loc[mask, 'latitude']  = lats   # Y Lambert → latitude

    pct = mask.sum() / len(df) * 100
    print(f"📍 Coordonnées valides : {mask.sum():,} / {len(df):,} ({pct:.1f}%)")
    return df


# ── Haversine vectorisé ────────────────────────────────────────────────────────
def haversine_vectorized(lat1: float, lon1: float,
                         lats: pd.Series, lons: pd.Series) -> pd.Series:
    """Retourne la distance en km entre (lat1, lon1) et chaque point du DataFrame."""
    lat1_r = np.radians(lat1)
    lon1_r = np.radians(lon1)
    lat2_r = np.radians(lats)
    lon2_r = np.radians(lons)

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = np.sin(dlat / 2)**2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2)**2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


# ── Filtre rayon ───────────────────────────────────────────────────────────────
def filter_by_radius(df: pd.DataFrame,
                     center_lat: float, center_lon: float,
                     radius_km: float) -> pd.DataFrame:
    df = df.dropna(subset=['latitude', 'longitude']).copy()
    df['distance_km'] = haversine_vectorized(
        center_lat, center_lon, df['latitude'], df['longitude']
    )
    return df[df['distance_km'] <= radius_km].sort_values('distance_km')


# ── Géocodage adresse → (lat, lon) via API BAN ────────────────────────────────
def geocode_address(address: str) -> tuple[float, float] | None:
    try:
        r = requests.get(
            "https://api-adresse.data.gouv.fr/search/",
            params={"q": address, "limit": 1},
            timeout=5
        )
        data = r.json()
        if data['features']:
            coords = data['features'][0]['geometry']['coordinates']
            return coords[1], coords[0]   # (lat, lon)
    except Exception as e:
        print(f"⚠️ Géocodage échoué : {e}")
    return None
