"""
statistics_analysis.py
======================
Comprehensive statistical analysis for the Nairobi Heat Vulnerability Assessment.

All analyses compare:
  - Informal settlements  (polygons from results/exposure/informal_settlements_obia_2024.geojson)
  - Rest of city          (everything inside Nairobi boundary that is NOT informal)

Both zones are further **masked by population density** so that pixels where
nobody lives (water, bare soil, parks) are excluded from the comparison.

Usage (from project root):
    python -m src.statistics_analysis
"""

import os
import sys
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.warp
from rasterio.features import rasterize
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy.interpolate import griddata
from scipy.stats import mannwhitneyu, ks_2samp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.common_helper import (
    PROJECT_ROOT, DATA_DIR, RESULTS_DIR,
    load_boundary, create_analysis_grid,
    PROXIMITY_CMAP, COMPOSITE_CMAP,
)
from src.adaptive_capacity_helper import compute_proximity, compute_road_density
from src.sensitivity_helper import resample_to_grid

# ── Output directory ────────────────────────────────────────────────────────
STATS_DIR = os.path.join(RESULTS_DIR, "statistics")
os.makedirs(STATS_DIR, exist_ok=True)

# ── Paths ────────────────────────────────────────────────────────────────────
INFORMAL_GEOJSON   = os.path.join(RESULTS_DIR, "exposure", "informal_settlements_obia_2024.geojson")
LST_2024           = os.path.join(PROJECT_ROOT, "notebooks", "results", "lst_geotiffs", "LST_2024.tif")
LST_2022           = os.path.join(PROJECT_ROOT, "notebooks", "results", "lst_geotiffs", "LST_2022.tif")
LST_2020           = os.path.join(PROJECT_ROOT, "notebooks", "results", "lst_geotiffs", "LST_2020.tif")
POP_GENERAL_TIF    = os.path.join(DATA_DIR, "sensitivity", "nairobi_general_pop_2020.tif")
POP_CHILDREN_TIF   = os.path.join(DATA_DIR, "sensitivity", "nairobi_children_pop_2020.tif")
POP_ELDERLY_TIF    = os.path.join(DATA_DIR, "sensitivity", "nairobi_elderly_pop_2020.tif")
RWI_CSV            = os.path.join(DATA_DIR, "sensitivity", "ken_relative_wealth_index.csv")
HEALTH_GEOJSON     = os.path.join(DATA_DIR, "adaptivity", "Health_facilities_Nairobi.geojson")
COOLING_GEOJSON    = os.path.join(DATA_DIR, "adaptivity", "cooling_centers_nairobi.geojson")
WATER_GEOJSON      = os.path.join(DATA_DIR, "adaptivity", "water_sources_nairobi.geojson")
GREEN_GEOJSON      = os.path.join(DATA_DIR, "adaptivity", "green_spaces_nairobi.geojson")
ROADS_GEOJSON      = os.path.join(DATA_DIR, "adaptivity", "major_roads.geojson")
STREETS_GEOJSON    = os.path.join(DATA_DIR, "adaptivity", "street_edges.geojson")


# ════════════════════════════════════════════════════════════════════════════
# SECTION 0 — Grid & masks
# ════════════════════════════════════════════════════════════════════════════

def build_masks(grid):
    """
    Build three boolean masks on the analysis grid:
      - informal_mask : cells covered by informal settlement polygons
      - formal_mask   : cells inside Nairobi but NOT informal AND where people live
      - pop_mask      : cells where population > 0 (used to filter uninhabited land)

    Returns dict with keys: 'informal', 'formal', 'pop', 'pop_array'
    """
    print("\n[0] Building spatial masks ...")

    # ── Informal settlement mask ────────────────────────────────────────────
    if not os.path.exists(INFORMAL_GEOJSON):
        raise FileNotFoundError(f"Informal settlements GeoJSON not found: {INFORMAL_GEOJSON}")

    informal_gdf = gpd.read_file(INFORMAL_GEOJSON).to_crs(grid["crs"])
    informal_raster = rasterize(
        [(geom, 1) for geom in informal_gdf.geometry if geom is not None],
        out_shape=(grid["nrows"], grid["ncols"]),
        transform=grid["transform"],
        fill=0, dtype="uint8",
    ).astype(bool)
    informal_mask = informal_raster & grid["mask"]

    # ── Population mask  ────────────────────────────────────────────────────
    pop_array = None
    pop_mask = grid["mask"].copy()   # default: all city cells count

    if os.path.exists(POP_GENERAL_TIF):
        raw = resample_to_grid(POP_GENERAL_TIF, grid, method=Resampling.sum)
        if raw is not None:
            pop_array = raw
            # inhabited = at least 1 person per 50×50 m cell
            pop_mask = (pop_array > 0) & grid["mask"]
            print(f"  Population mask: {pop_mask.sum():,} inhabited cells "
                  f"({pop_mask.sum() / grid['mask'].sum() * 100:.1f}% of city)")
    else:
        print("  WARNING: population raster not found — using full city boundary as mask")

    # ── Formal mask = inside city + inhabited + NOT informal ────────────────
    formal_mask = pop_mask & ~informal_mask

    # Apply pop_mask to informal too
    informal_mask = informal_mask & pop_mask

    print(f"  Informal cells: {informal_mask.sum():,}")
    print(f"  Formal cells:   {formal_mask.sum():,}")

    return {
        "informal": informal_mask,
        "formal":   formal_mask,
        "pop":      pop_mask,
        "pop_array": pop_array,
    }


# ════════════════════════════════════════════════════════════════════════════
# SECTION 1 — EXPOSURE: Land Surface Temperature
# ════════════════════════════════════════════════════════════════════════════

def _load_lst(tif_path, grid):
    """Reproject LST GeoTIFF onto the analysis grid (bilinear)."""
    with rasterio.open(tif_path) as src:
        dst = np.full((grid["nrows"], grid["ncols"]), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            resampling=Resampling.bilinear,
        )
        dst[~grid["mask"]] = np.nan
    return dst


def _lst_stats(values, label):
    """Compute a rich set of statistics for a 1-D array of LST values."""
    v = values[np.isfinite(values)]
    if len(v) == 0:
        return {}
    return {
        "zone": label,
        "n_cells": len(v),
        "mean_C": float(np.mean(v)),
        "median_C": float(np.median(v)),
        "std_C": float(np.std(v)),
        "min_C": float(np.min(v)),
        "max_C": float(np.max(v)),
        "p10_C": float(np.percentile(v, 10)),
        "p25_C": float(np.percentile(v, 25)),
        "p75_C": float(np.percentile(v, 75)),
        "p90_C": float(np.percentile(v, 90)),
        "p95_C": float(np.percentile(v, 95)),
        "p99_C": float(np.percentile(v, 99)),
    }


def analyse_lst(grid, masks, year=2024):
    """
    Section 1 — LST statistics split by informal vs. formal, for a given year.

    Returns a DataFrame with one row per zone.
    """
    tif_map = {2020: LST_2020, 2022: LST_2022, 2024: LST_2024}
    tif = tif_map[year]

    print(f"\n[1] LST analysis — {year} ...")
    if not os.path.exists(tif):
        print(f"  WARNING: {tif} not found, skipping.")
        return None

    lst = _load_lst(tif, grid)

    rows = []
    for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
        vals = lst[mask]
        row = _lst_stats(vals, zone)
        row["year"] = year
        rows.append(row)

    df = pd.DataFrame(rows)

    # ── Informal vs formal temperature gap ──────────────────────────────────
    inf_vals = lst[masks["informal"]]
    for_vals = lst[masks["formal"]]
    inf_vals = inf_vals[np.isfinite(inf_vals)]
    for_vals = for_vals[np.isfinite(for_vals)]

    delta = np.mean(inf_vals) - np.mean(for_vals)
    print(f"  Informal mean LST ({year}): {np.mean(inf_vals):.2f} °C")
    print(f"  Formal   mean LST ({year}): {np.mean(for_vals):.2f} °C")
    print(f"  Informal - Formal gap:      {delta:+.2f} °C")

    # ── Statistical test (Mann-Whitney U) ───────────────────────────────────
    if len(inf_vals) > 1 and len(for_vals) > 1:
        stat, pval = mannwhitneyu(inf_vals, for_vals, alternative="two-sided")
        print(f"  Mann-Whitney U test:  U={stat:.0f}, p={pval:.2e}")
        for row in rows:
            row["mwu_pvalue"] = pval

    # ── KS test ─────────────────────────────────────────────────────────────
    if len(inf_vals) > 1 and len(for_vals) > 1:
        ks_stat, ks_pval = ks_2samp(inf_vals, for_vals)
        print(f"  KS test:  D={ks_stat:.4f}, p={ks_pval:.2e}")

    # ── Save ─────────────────────────────────────────────────────────────────
    df.to_csv(os.path.join(STATS_DIR, f"lst_stats_{year}.csv"), index=False)

    # ── Figure: violin + box plot ─────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Violin
    parts = axes[0].violinplot(
        [inf_vals[::10], for_vals[::10]],   # downsample for speed
        positions=[1, 2], showmedians=True, showextrema=True
    )
    colors = ["#d73027", "#4393c3"]
    for pc, col in zip(parts["bodies"], colors):
        pc.set_facecolor(col); pc.set_alpha(0.7)
    axes[0].set_xticks([1, 2])
    axes[0].set_xticklabels(["Informal", "Formal"])
    axes[0].set_ylabel("LST (°C)")
    axes[0].set_title(f"LST Distribution by Settlement Type ({year})", fontweight="bold")
    axes[0].grid(axis="y", linestyle="--", alpha=0.4)

    # Histogram overlay
    axes[1].hist(inf_vals, bins=80, density=True, alpha=0.6, color="#d73027", label="Informal")
    axes[1].hist(for_vals, bins=80, density=True, alpha=0.6, color="#4393c3", label="Formal")
    axes[1].axvline(np.mean(inf_vals), color="#d73027", linestyle="--", linewidth=1.5,
                    label=f"Informal mean = {np.mean(inf_vals):.1f} °C")
    axes[1].axvline(np.mean(for_vals), color="#4393c3", linestyle="--", linewidth=1.5,
                    label=f"Formal mean = {np.mean(for_vals):.1f} °C")
    axes[1].set_xlabel("LST (°C)")
    axes[1].set_ylabel("Density")
    axes[1].set_title(f"LST Histogram ({year})", fontweight="bold")
    axes[1].legend(fontsize=9)
    axes[1].grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    fig.savefig(os.path.join(STATS_DIR, f"lst_distribution_{year}.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved → results/statistics/lst_stats_{year}.csv + lst_distribution_{year}.png")

    return df


def analyse_lst_all_years(grid, masks):
    """Run LST analysis for 2020, 2022 and 2024 and produce a temporal trend chart."""
    print("\n[1b] Multi-year LST trend ...")
    rows = []
    for year in [2020, 2022, 2024]:
        df = analyse_lst(grid, masks, year=year)
        if df is not None:
            rows.append(df)

    if not rows:
        return None
    combined = pd.concat(rows, ignore_index=True)

    # Trend figure
    fig, ax = plt.subplots(figsize=(9, 5))
    for zone, col in [("Informal", "#d73027"), ("Formal (non-informal)", "#4393c3")]:
        sub = combined[combined["zone"] == zone]
        if sub.empty:
            continue
        ax.plot(sub["year"], sub["mean_C"], "o-", color=col, linewidth=2,
                markersize=7, label=f"{zone} — mean")
        ax.fill_between(sub["year"],
                        sub["mean_C"] - sub["std_C"],
                        sub["mean_C"] + sub["std_C"],
                        color=col, alpha=0.15)
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean LST (°C)")
    ax.set_title("LST Trend: Informal vs. Formal (inhabited pixels only)", fontweight="bold")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.4)
    plt.tight_layout()
    fig.savefig(os.path.join(STATS_DIR, "lst_trend_2020_2024.png"), dpi=150)
    plt.close(fig)

    combined.to_csv(os.path.join(STATS_DIR, "lst_stats_all_years.csv"), index=False)
    print("  Saved → results/statistics/lst_trend_2020_2024.png + lst_stats_all_years.csv")
    return combined


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2 — SENSITIVITY: Population & Wealth
# ════════════════════════════════════════════════════════════════════════════

def analyse_sensitivity(grid, masks):
    """
    Section 2 — Population counts and wealth by settlement class.

    Returns a summary DataFrame.
    """
    print("\n[2] Sensitivity analysis (population & wealth) ...")
    pixel_area_ha = (grid["resolution"] ** 2) / 10000.0
    rows = []

    def pop_stats(pop_raster, pop_name, masks):
        results = []
        for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
            vals = pop_raster[mask]
            vals = vals[np.isfinite(vals)]
            total = float(np.nansum(vals))
            results.append({
                "zone": zone,
                "population_layer": pop_name,
                "total_count": total,
                "n_inhabited_cells": int(np.sum(vals > 0)),
                "area_ha": float(np.sum(mask)) * pixel_area_ha,
                "pop_density_per_ha": total / (float(np.sum(mask)) * pixel_area_ha) if np.sum(mask) > 0 else np.nan,
                "mean_per_cell": float(np.mean(vals)) if len(vals) else np.nan,
            })
        return results

    # General population
    if os.path.exists(POP_GENERAL_TIF):
        pop_gen = resample_to_grid(POP_GENERAL_TIF, grid, method=Resampling.sum)
        if pop_gen is not None:
            rows.extend(pop_stats(pop_gen, "general", masks))
            # Population-weighted LST (section 2b)
            _pop_weighted_lst(grid, masks, pop_gen, year=2024)

    # Children < 5
    if os.path.exists(POP_CHILDREN_TIF):
        pop_ch = resample_to_grid(POP_CHILDREN_TIF, grid, method=Resampling.sum)
        if pop_ch is not None:
            rows.extend(pop_stats(pop_ch, "children_u5", masks))

    # Elderly 65+
    if os.path.exists(POP_ELDERLY_TIF):
        pop_el = resample_to_grid(POP_ELDERLY_TIF, grid, method=Resampling.sum)
        if pop_el is not None:
            rows.extend(pop_stats(pop_el, "elderly_65plus", masks))

    df_pop = pd.DataFrame(rows)
    df_pop.to_csv(os.path.join(STATS_DIR, "sensitivity_population_stats.csv"), index=False)

    # ── Relative Wealth Index ────────────────────────────────────────────────
    df_wealth = None
    if os.path.exists(RWI_CSV):
        boundary = load_boundary()
        rwi_df = pd.read_csv(RWI_CSV)
        rwi_gdf = gpd.GeoDataFrame(
            rwi_df,
            geometry=gpd.points_from_xy(rwi_df.longitude, rwi_df.latitude),
            crs="EPSG:4326",
        )
        rwi_nairobi = gpd.clip(rwi_gdf, boundary)
        rwi_utm = rwi_nairobi.to_crs(grid["crs"])

        # Interpolate onto grid
        minx, miny, maxx, maxy = grid["bounds"]
        grid_x, grid_y = np.mgrid[
            minx:maxx:complex(0, grid["ncols"]),
            maxy:miny:complex(0, grid["nrows"]),
        ]
        points = np.column_stack([rwi_utm.geometry.x, rwi_utm.geometry.y])
        values = rwi_utm["rwi"].values
        grid_rwi_T = griddata(points, values,
                              (grid_x, grid_y), method="linear")
        grid_rwi = grid_rwi_T.T
        grid_rwi[~grid["mask"]] = np.nan

        rwi_rows = []
        for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
            v = grid_rwi[mask]
            v = v[np.isfinite(v)]
            if len(v) == 0:
                continue
            rwi_rows.append({
                "zone": zone,
                "n_points": len(v),
                "mean_rwi": float(np.mean(v)),
                "median_rwi": float(np.median(v)),
                "std_rwi": float(np.std(v)),
                "p10_rwi": float(np.percentile(v, 10)),
                "p90_rwi": float(np.percentile(v, 90)),
                "pct_below_neg05": float(np.mean(v < -0.5) * 100),
                "pct_above_05": float(np.mean(v > 0.5) * 100),
            })
            print(f"  RWI {zone}: mean={np.mean(v):.3f}, median={np.median(v):.3f}")

        df_wealth = pd.DataFrame(rwi_rows)
        df_wealth.to_csv(os.path.join(STATS_DIR, "sensitivity_wealth_stats.csv"), index=False)

        # Figure
        fig, ax = plt.subplots(figsize=(9, 5))
        for zone, col in [("Informal", "#d73027"), ("Formal (non-informal)", "#4393c3")]:
            for mask_zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
                if zone != mask_zone:
                    continue
                v = grid_rwi[mask]
                v = v[np.isfinite(v)]
                ax.hist(v, bins=60, density=True, alpha=0.6, color=col, label=zone)
                ax.axvline(np.mean(v), color=col, linestyle="--", linewidth=1.5)
        ax.set_xlabel("Relative Wealth Index")
        ax.set_ylabel("Density")
        ax.set_title("Relative Wealth Index Distribution", fontweight="bold")
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(STATS_DIR, "sensitivity_wealth_distribution.png"), dpi=150)
        plt.close(fig)

    print(f"  Saved → results/statistics/sensitivity_population_stats.csv")
    if df_wealth is not None:
        print(f"  Saved → results/statistics/sensitivity_wealth_stats.csv")
    return df_pop, df_wealth


def _pop_weighted_lst(grid, masks, pop_array, year=2024):
    """Compute population-weighted mean LST per zone (section 2b)."""
    tif_map = {2020: LST_2020, 2022: LST_2022, 2024: LST_2024}
    tif = tif_map.get(year)
    if tif is None or not os.path.exists(tif):
        return
    lst = _load_lst(tif, grid)
    rows = []
    for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
        t = lst[mask]
        p = pop_array[mask]
        valid = np.isfinite(t) & np.isfinite(p) & (p > 0)
        if valid.sum() == 0:
            continue
        pw_mean = float(np.sum(t[valid] * p[valid]) / np.sum(p[valid]))
        rows.append({"zone": zone, "year": year, "pop_weighted_mean_lst_C": pw_mean})
        print(f"  Pop-weighted LST {zone} ({year}): {pw_mean:.2f} °C")

    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(STATS_DIR, f"sensitivity_pop_weighted_lst_{year}.csv"), index=False)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ADAPTIVE CAPACITY: Access metrics
# ════════════════════════════════════════════════════════════════════════════

def _proximity_stats(proximity_raster, zone_label, mask, grid, max_dist_m=None):
    """
    Convert proximity score back to approximate distance (metres) and compute stats.
    proximity = 1 - dist/max_dist  →  dist = (1-proximity)*max_dist
    If max_dist_m is None we report the normalised proximity score (0-1) directly.
    """
    vals = proximity_raster[mask]
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return {}

    if max_dist_m is not None:
        dist_m = (1 - vals) * max_dist_m
        return {
            "zone": zone_label,
            "mean_dist_m": float(np.mean(dist_m)),
            "median_dist_m": float(np.median(dist_m)),
            "std_dist_m": float(np.std(dist_m)),
            "p25_dist_m": float(np.percentile(dist_m, 25)),
            "p75_dist_m": float(np.percentile(dist_m, 75)),
            "pct_within_500m": float(np.mean(dist_m < 500) * 100),
            "pct_within_1km": float(np.mean(dist_m < 1000) * 100),
            "pct_within_2km": float(np.mean(dist_m < 2000) * 100),
            "pct_within_5km": float(np.mean(dist_m < 5000) * 100),
        }
    else:
        return {
            "zone": zone_label,
            "mean_score": float(np.mean(vals)),
            "median_score": float(np.median(vals)),
            "std_score": float(np.std(vals)),
            "p10_score": float(np.percentile(vals, 10)),
            "p90_score": float(np.percentile(vals, 90)),
        }


def analyse_adaptive_capacity(grid, masks):
    """
    Section 3 — Adaptive capacity: proximity metrics by settlement class.

    Returns a DataFrame of access statistics.
    """
    print("\n[3] Adaptive capacity analysis ...")
    all_rows = []

    layers_config = [
        # (label, geojson_path, max_dist_m_for_interpretation, filter_fn)
        ("Health facilities",   HEALTH_GEOJSON,   10000, lambda gdf: gdf[gdf.get("Province", pd.Series(["NAIROBI"] * len(gdf))) == "NAIROBI"] if "Province" in gdf.columns else gdf),
        ("Cooling centres",     COOLING_GEOJSON,  5000,  None),
        ("Water sources",       WATER_GEOJSON,    2000,  None),
        ("Green spaces",        GREEN_GEOJSON,    5000,  None),
    ]

    for label, path, max_dist_m, filter_fn in layers_config:
        if not os.path.exists(path):
            print(f"  SKIP {label}: file not found")
            continue
        gdf = gpd.read_file(path)
        if filter_fn is not None:
            gdf = filter_fn(gdf)
        print(f"  {label}: {len(gdf)} features")
        prox = compute_proximity(gdf, grid)

        for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
            row = _proximity_stats(prox, zone, mask, grid, max_dist_m=max_dist_m)
            row["layer"] = label
            all_rows.append(row)

    # ── Road density ─────────────────────────────────────────────────────────
    if os.path.exists(ROADS_GEOJSON):
        roads = gpd.read_file(ROADS_GEOJSON)
        extra = []
        if os.path.exists(STREETS_GEOJSON):
            streets = gpd.read_file(STREETS_GEOJSON)
            import pandas as _pd
            roads = gpd.GeoDataFrame(
                _pd.concat([roads[["geometry"]], streets[["geometry"]]], ignore_index=True),
                crs=roads.crs
            )
        road_density = compute_road_density(roads, grid, bandwidth_m=500)
        for zone, mask in [("Informal", masks["informal"]), ("Formal (non-informal)", masks["formal"])]:
            vals = road_density[mask]
            vals = vals[np.isfinite(vals)]
            row = {
                "layer": "Road density",
                "zone": zone,
                "mean_score": float(np.mean(vals)) if len(vals) else np.nan,
                "median_score": float(np.median(vals)) if len(vals) else np.nan,
                "std_score": float(np.std(vals)) if len(vals) else np.nan,
            }
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    df.to_csv(os.path.join(STATS_DIR, "adaptive_capacity_stats.csv"), index=False)
    print("  Saved → results/statistics/adaptive_capacity_stats.csv")

    # ── Bar chart: mean distance to each service ─────────────────────────────
    dist_cols = [c for c in df.columns if c.startswith("mean_dist_m")]
    if dist_cols and "mean_dist_m" in df.columns:
        dist_df = df[df["mean_dist_m"].notna()].copy()
        layers_order = dist_df["layer"].unique()
        x = np.arange(len(layers_order))
        width = 0.35
        fig, ax = plt.subplots(figsize=(11, 6))
        for i, (zone, col) in enumerate([("Informal", "#d73027"), ("Formal (non-informal)", "#4393c3")]):
            sub = dist_df[dist_df["zone"] == zone]
            vals_plot = [sub[sub["layer"] == l]["mean_dist_m"].values[0] if len(sub[sub["layer"] == l]) else 0 for l in layers_order]
            ax.bar(x + i * width, vals_plot, width, label=zone, color=col, alpha=0.8)
        ax.set_xticks(x + width / 2)
        ax.set_xticklabels(layers_order, rotation=15, ha="right")
        ax.set_ylabel("Mean distance (m)")
        ax.set_title("Mean Distance to Services: Informal vs. Formal", fontweight="bold")
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(STATS_DIR, "adaptive_capacity_distance_comparison.png"), dpi=150)
        plt.close(fig)

    return df


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4 — ALL-IN-ONE SUMMARY TABLE
# ════════════════════════════════════════════════════════════════════════════

def build_summary_table(grid, masks, lst_df=None, pop_df=None, wealth_df=None, ac_df=None):
    """
    Produce a single wide-format summary table combining all sections,
    with one row per zone (Informal / Formal).
    """
    print("\n[4] Building all-in-one summary table ...")
    rows = []

    for zone in ["Informal", "Formal (non-informal)"]:
        mask = masks["informal"] if zone == "Informal" else masks["formal"]
        pixel_area_ha = (grid["resolution"] ** 2) / 10000.0
        r = {"zone": zone, "area_ha": float(np.sum(mask)) * pixel_area_ha}

        # LST 2024
        if lst_df is not None:
            sub = lst_df[(lst_df["zone"] == zone) & (lst_df["year"] == 2024)]
            if not sub.empty:
                r["lst_mean_C"] = sub["mean_C"].values[0]
                r["lst_median_C"] = sub["median_C"].values[0]
                r["lst_std_C"] = sub["std_C"].values[0]
                r["lst_p95_C"] = sub["p95_C"].values[0]

        # Population
        if pop_df is not None:
            sub = pop_df[(pop_df["zone"] == zone) & (pop_df["population_layer"] == "general")]
            if not sub.empty:
                r["total_population"] = sub["total_count"].values[0]
                r["pop_density_per_ha"] = sub["pop_density_per_ha"].values[0]
            sub_ch = pop_df[(pop_df["zone"] == zone) & (pop_df["population_layer"] == "children_u5")]
            if not sub_ch.empty:
                r["children_u5_count"] = sub_ch["total_count"].values[0]
            sub_el = pop_df[(pop_df["zone"] == zone) & (pop_df["population_layer"] == "elderly_65plus")]
            if not sub_el.empty:
                r["elderly_65plus_count"] = sub_el["total_count"].values[0]

        # Wealth
        if wealth_df is not None:
            sub = wealth_df[wealth_df["zone"] == zone]
            if not sub.empty:
                r["rwi_mean"] = sub["mean_rwi"].values[0]
                r["rwi_median"] = sub["median_rwi"].values[0]
                r["pct_very_poor_below_neg05"] = sub["pct_below_neg05"].values[0]

        # Adaptive capacity
        if ac_df is not None:
            for layer in ac_df["layer"].unique():
                sub = ac_df[(ac_df["zone"] == zone) & (ac_df["layer"] == layer)]
                if sub.empty:
                    continue
                key_prefix = layer.lower().replace(" ", "_").replace("&", "and")
                if "mean_dist_m" in sub.columns and not sub["mean_dist_m"].isna().all():
                    r[f"{key_prefix}_mean_dist_m"] = sub["mean_dist_m"].values[0]
                    if "pct_within_1km" in sub.columns:
                        r[f"{key_prefix}_pct_within_1km"] = sub["pct_within_1km"].values[0]
                elif "mean_score" in sub.columns:
                    r[f"{key_prefix}_score"] = sub["mean_score"].values[0]

        rows.append(r)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(STATS_DIR, "all_in_one_summary.csv"), index=False)
    print("  Saved → results/statistics/all_in_one_summary.csv")
    return df


# ════════════════════════════════════════════════════════════════════════════
# SECTION 5 — ALL-IN-ONE VISUAL DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

def plot_summary_dashboard(summary_df, lst_multi_df=None):
    """
    One-page summary figure: 4 panels.
    """
    print("\n[5] Generating summary dashboard ...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Nairobi Heat Vulnerability — Key Statistics (2024)",
                 fontsize=16, fontweight="bold", y=0.98)

    colors = {"Informal": "#d73027", "Formal (non-informal)": "#4393c3"}
    zones = list(summary_df["zone"])

    # Panel A: LST comparison
    ax = axes[0, 0]
    if "lst_mean_C" in summary_df.columns:
        means = summary_df["lst_mean_C"].values
        stds  = summary_df["lst_std_C"].values if "lst_std_C" in summary_df.columns else [0, 0]
        bars = ax.bar(zones, means, color=[colors[z] for z in zones], alpha=0.8, width=0.5)
        ax.errorbar(zones, means, yerr=stds, fmt="none", color="black", capsize=6, linewidth=1.5)
        for bar, val in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.1, f"{val:.1f} °C",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Mean LST (°C)")
        ax.set_title("A — Land Surface Temperature (2024)", fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Panel B: Population density
    ax = axes[0, 1]
    if "pop_density_per_ha" in summary_df.columns:
        dens = summary_df["pop_density_per_ha"].values
        ax.bar(zones, dens, color=[colors[z] for z in zones], alpha=0.8, width=0.5)
        for i, val in enumerate(dens):
            ax.text(i, val + 0.5, f"{val:.1f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Population density (people/ha)")
        ax.set_title("B — Population Density", fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Panel C: Relative Wealth Index
    ax = axes[1, 0]
    if "rwi_mean" in summary_df.columns:
        rwi = summary_df["rwi_mean"].values
        ax.bar(zones, rwi, color=[colors[z] for z in zones], alpha=0.8, width=0.5)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        for i, val in enumerate(rwi):
            ax.text(i, val + 0.01, f"{val:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Mean Relative Wealth Index")
        ax.set_title("C — Relative Wealth Index (Sensitivity)", fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Panel D: Distance to health facility
    ax = axes[1, 1]
    if "health_facilities_mean_dist_m" in summary_df.columns:
        dists = summary_df["health_facilities_mean_dist_m"].values
        ax.bar(zones, dists, color=[colors[z] for z in zones], alpha=0.8, width=0.5)
        for i, val in enumerate(dists):
            ax.text(i, val + 10, f"{val:.0f} m", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Mean distance (m)")
        ax.set_title("D — Distance to Nearest Health Facility", fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    fig.savefig(os.path.join(STATS_DIR, "summary_dashboard.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Saved → results/statistics/summary_dashboard.png")


# ════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def run_all():
    print("=" * 60)
    print("  NAIROBI HEAT VULNERABILITY — FULL STATISTICS ANALYSIS")
    print("=" * 60)

    # Setup grid
    boundary = load_boundary()
    grid = create_analysis_grid(boundary, resolution_m=50)

    # Build masks
    masks = build_masks(grid)

    # Section 1 — Exposure (LST for 2024 + multi-year trend)
    lst_2024_df = analyse_lst(grid, masks, year=2024)
    lst_all_df  = analyse_lst_all_years(grid, masks)

    # Section 2 — Sensitivity (population + wealth)
    pop_df, wealth_df = analyse_sensitivity(grid, masks)

    # Section 3 — Adaptive capacity (access metrics)
    ac_df = analyse_adaptive_capacity(grid, masks)

    # Section 4 — All-in-one summary table
    summary = build_summary_table(grid, masks,
                                  lst_df=lst_all_df,
                                  pop_df=pop_df,
                                  wealth_df=wealth_df,
                                  ac_df=ac_df)

    # Section 5 — Dashboard figure
    plot_summary_dashboard(summary, lst_multi_df=lst_all_df)

    print("\n" + "=" * 60)
    print("  ALL DONE — outputs in results/statistics/")
    print("=" * 60)
    print(summary.to_string(index=False))
    return summary


if __name__ == "__main__":
    run_all()
