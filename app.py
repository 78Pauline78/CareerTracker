import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from utils.geo import geocode_address, filter_by_radius

# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Entreprises IDF",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Cartographie des Entreprises — Île-de-France")

# ── Chargement des données ────────────────────────────────────────────────────
@st.cache_data(show_spinner="Chargement des données...")
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=',', dtype=str, low_memory=False)
    df['latitude']     = pd.to_numeric(df['latitude'],     errors='coerce')
    df['longitude']    = pd.to_numeric(df['longitude'],    errors='coerce')
    df['non_entreprise']          = df['non_entreprise'].fillna('Nom inconnu')
    df['adresse']      = df['adresse'].fillna('')
    return df.dropna(subset=['latitude', 'longitude'])

df = load_data("data/resultat_idf.csv")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Paramètres")

    adresse_input = st.text_input(
        "📍 Adresse de référence",
        placeholder="Ex: 1 Place du Parvis Notre-Dame, Paris"
    )

    rayon_km = st.slider("📏 Rayon (km)", min_value=1, max_value=50, value=10)

    # Filtre secteurs NAF
    naf_list = sorted(df['niv1_act_lib'].dropna().unique())
    secteurs = st.multiselect(
        "🏷️ Codes NAF (vide = tous)",
        options=naf_list,
        default=[]
    )

    max_markers = st.slider(
        "🗺️ Nb max de points affichés sur la carte",
        min_value=100, max_value=5000, value=1000, step=100
    )

    btn = st.button("🔍 Lancer la recherche", type="primary", use_container_width=True)

# ── Recherche ─────────────────────────────────────────────────────────────────
if btn:
    if not adresse_input.strip():
        st.warning("Veuillez saisir une adresse.")
        st.stop()

    with st.spinner("Géocodage de l'adresse..."):
        coords = geocode_address(adresse_input)

    if coords is None:
        st.error("❌ Adresse introuvable. Essayez d'être plus précis.")
        st.stop()

    center_lat, center_lon = coords
    st.success(f"📍 Adresse localisée : {center_lat:.5f}, {center_lon:.5f}")

    # Filtre secteur
    df_filtered = df.copy()
    if secteurs:
        df_filtered = df_filtered[df_filtered['niv1_act_lib'].isin(secteurs)]

    # Filtre rayon
    with st.spinner("Calcul des distances..."):
        df_result = filter_by_radius(df_filtered, center_lat, center_lon, rayon_km)

    st.markdown(f"## 🎯 **{len(df_result):,}** entreprises trouvées dans un rayon de **{rayon_km} km**")

    # ── Carte ─────────────────────────────────────────────────────────────────
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='CartoDB positron'
    )

    # Marqueur adresse de référence
    folium.Marker(
        location=[center_lat, center_lon],
        tooltip="📍 Votre adresse",
        icon=folium.Icon(color='blue', icon='home', prefix='fa')
    ).add_to(m)

    # Cercle de rayon
    folium.Circle(
        location=[center_lat, center_lon],
        radius=rayon_km * 1000,
        color='#3b82f6',
        weight=2,
        fill=True,
        fill_opacity=0.05
    ).add_to(m)

    # ── Points entreprises avec tooltip + popup ────────────────────────────
    df_map = df_result.head(max_markers)

    for _, row in df_map.iterrows():
        nom     = row['non_entreprise']
        naf     = row.get('niv1_act_lib', '')
        adresse = row.get('adresse', '')
        cp      = row.get('codePostalEtablissement', '')
        ville   = row.get('libelleCommuneEtablissement', '')
        dist    = row.get('distance_km', 0)
        siret   = row.get('siret', '')

        # Tooltip = affiché au SURVOL (léger)
        tooltip_html = f"<b>{nom}</b><br>📏 {dist:.1f} km"

        # Popup = affiché au CLIC (détaillé)
        popup_html = f"""
        <div style="font-family:Arial; min-width:200px; font-size:13px;">
            <b style="font-size:14px;">{nom}</b><br>
            <hr style="margin:4px 0">
            🏷️ <b>NAF :</b> {naf}<br>
            📍 <b>Adresse :</b> {adresse}<br>
            🏙️ {cp} {ville}<br>
            📏 <b>Distance :</b> {dist:.1f} km<br>
            🔢 <b>SIRET :</b> {siret}
        </div>
        """

        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=6,
            color='#dc2626',
            fill=True,
            fill_color='#ef4444',
            fill_opacity=0.8,
            weight=1,
            tooltip=folium.Tooltip(tooltip_html, sticky=True),   # ← survol
            popup=folium.Popup(popup_html, max_width=280)         # ← clic
        ).add_to(m)

    st_folium(m, width="100%", height=550, returned_objects=[])

    # ── Tableau ───────────────────────────────────────────────────────────────
    st.markdown("### 📋 Liste des entreprises")

    cols_display = ['non_entreprise', 'niv1_act_lib', 'adresse',
                    'codePostalEtablissement', 'libelleCommuneEtablissement',
                    'distance_km', 'siret']
    cols_display = [c for c in cols_display if c in df_result.columns]

    st.dataframe(
        df_result[cols_display]
            .rename(columns={
                'niv1_act_lib': 'Lib NAF',
                'codePostalEtablissement': 'CP',
                'libelleCommuneEtablissement': 'Ville',
                'distance_km': 'Distance (km)'
            })
            .style.format({'Distance (km)': '{:.1f}'}),
        use_container_width=True,
        height=400
    )

    # ── Export ────────────────────────────────────────────────────────────────
    csv = df_result[cols_display].to_csv(index=False, sep=';').encode('utf-8')
    st.download_button(
        label="⬇️ Exporter en CSV",
        data=csv,
        file_name=f"entreprises_{rayon_km}km.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    st.info("👈 Configurez vos paramètres dans la sidebar et cliquez sur **Lancer la recherche**")
    st.markdown("""
    | Interaction | Action |
    |---|---|
    | **Survol** d'un point | Affiche le nom de l'entreprise |
    | **Clic** sur un point | Affiche NAF, adresse, distance, SIRET |
    """)
