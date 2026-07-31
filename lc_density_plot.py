#!/usr/bin/env python3
"""
GRB Light Curve Density Distribution + SVOM/VT VT_R overlay

Background: Swift R-band (or i/z-band) 2D density histogram
Foreground: SVOM/VT VT_R detections (red) and upper limits (green)
"""

import os
import glob
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

# ---- Config ----
GRBLC_MAG_DIR = "/Users/xlp/Documents/trae_projects/grblc/grbLC/grblc/data/mag_files"
OUT_DIR = "/Users/xlp/Documents/trae_projects/VT_GCN_history/doc_figures"
os.makedirs(OUT_DIR, exist_ok=True)

R_BANDS = {"R", "Rc", "r'", "r", "CR"}
IZ_BANDS = {"i", "i'", "I", "Ic", "z", "z'", "J", "H", "K", "Ks"}


def load_swift_bands(band_set):
    """Load light curve data for the given band set."""
    files = sorted(glob.glob(os.path.join(GRBLC_MAG_DIR, "*_mag.txt")))
    all_t, all_mag, all_name = [], [], []
    grb_names, grb_peak_info = [], {}

    for fp in files:
        grb_name = os.path.basename(fp).replace("_mag.txt", "")
        grb_names.append(grb_name)
        grb_t, grb_mag = [], []
        try:
            with open(fp, "r", errors="ignore") as f:
                f.readline()
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) < 5:
                        continue
                    try:
                        t, mag = float(parts[0]), float(parts[1])
                    except ValueError:
                        continue
                    band = parts[3].strip()
                    if band not in band_set:
                        continue
                    if t <= 0 or mag <= 0 or mag >= 30:
                        continue
                    grb_t.append(t)
                    grb_mag.append(mag)
            if not grb_t:
                continue
            grb_t, grb_mag = np.array(grb_t), np.array(grb_mag)
            all_t.extend(grb_t)
            all_mag.extend(grb_mag)
            all_name.extend([grb_name] * len(grb_t))
            idx = np.argmin(grb_mag)
            grb_peak_info[grb_name] = (grb_t[idx], grb_mag[idx])
        except Exception:
            continue
    return np.array(all_t), np.array(all_mag), all_name, grb_names, grb_peak_info


def load_svom_vt_r():
    """Load SVOM/VT VT_R detections and upper limits (SVOM-triggered only).
    Also returns is_auto_followup flag for each point.
    """
    import sys
    sys.path.insert(0, "/Users/xlp/Documents/trae_projects/VT_GCN_history")
    from vt_store import get_store

    store = get_store()
    recs = store.all_records()

    det_t, det_mag, det_name = [], [], []
    ul_t, ul_mag, ul_name, ul_auto = [], [], [], []

    for r in recs:
        # Only SVOM/ECLAIRs triggered events
        src = r.get("trigger_source", "") or ""
        if not src.startswith("SVOM"):
            continue
        # Exclude stellar flares and other non-GRB events
        rtype = r.get("report_type", "") or ""
        if rtype in ("stellar_flare", "clarification"):
            continue
        event = r.get("event_name") or r.get("eventId") or ""
        # Check if this is auto followup
        d = r.get("trigger_to_obs_hr")
        is_af = (isinstance(d, (int, float)) and 0 < d <= 1.0) or r.get("is_auto_followup")
        for m in r.get("magnitudes", []):
            if m.get("band") != "VT_R":
                continue
            t_mid = m.get("t_mid_hr")
            val = m.get("value")
            if t_mid is None or val is None:
                continue
            t_sec = t_mid * 3600.0
            if t_sec <= 0 or val <= 0 or val >= 30:
                continue
            if m.get("is_limit"):
                ul_t.append(t_sec)
                ul_mag.append(val)
                ul_name.append(event)
                ul_auto.append(is_af)
            else:
                det_t.append(t_sec)
                det_mag.append(val)
                det_name.append(event)

    return (
        np.array(det_t), np.array(det_mag), det_name,
        np.array(ul_t), np.array(ul_mag), ul_name, ul_auto,
    )


def _place_labels_below(ax, points, color, t_range=(50, 1e6), max_labels=30):
    """
    Place labels near each data point, position depends on time:
    - Early points: label to the lower-left
    - Middle points: label below or above (alternating)
    - Late points: label to the lower-right
    Collision detection prevents overlap.
    """
    if not points:
        return

    # Sort by time
    points.sort(key=lambda p: p[0])
    points = points[:max_labels]

    n = len(points)
    if n == 0:
        return

    log_t_min = np.log10(t_range[0])
    log_t_max = np.log10(t_range[1])

    # Collision detection boxes: (log_t_lo, log_t_hi, mag_lo, mag_hi)
    placed_boxes = []
    label_w = 0.35  # log-time width of a label
    label_h = 0.7   # mag height of a label

    placed_count = 0
    for i, (t, m, name) in enumerate(points):
        if placed_count >= max_labels:
            break
        log_t = np.log10(t)

        # Determine position zone: early / middle / late
        frac = (log_t - log_t_min) / (log_t_max - log_t_min)
        if frac < 0.2:
            # Early: prefer lower-left
            candidates = [
                (-0.55, 2.0),   # left-down far
                (-0.45, 1.5),   # left-down
                (-0.55, 3.0),   # left-down very far
                (0.0, 2.5),     # below
                (0.4, 1.5),     # right-down fallback
            ]
        elif frac > 0.8:
            # Late: prefer lower-right
            candidates = [
                (0.55, 2.0),    # right-down far
                (0.45, 1.5),    # right-down
                (0.55, 3.0),    # right-down very far
                (0.0, 2.5),     # below
                (-0.4, 1.5),    # left-down fallback
            ]
        else:
            # Middle: alternate below and above
            if i % 2 == 0:
                candidates = [
                    (0.0, 2.0),      # below
                    (0.35, 1.5),     # right-down
                    (-0.35, 1.5),    # left-down
                    (0.0, 3.0),      # below far
                    (-0.4, 2.5),     # left-down far
                ]
            else:
                candidates = [
                    (0.0, -1.8),     # above
                    (0.35, -1.5),    # right-up
                    (-0.35, -1.5),   # left-up
                    (0.0, -2.5),     # above far
                    (0.4, -1.8),     # right-up far
                ]

        best_pos = None
        for dt, dm in candidates:
            lc_t = log_t + dt
            lc_m = m + dm
            box_t_lo = lc_t - label_w / 2
            box_t_hi = lc_t + label_w / 2
            box_m_lo = lc_m - label_h / 2
            box_m_hi = lc_m + label_h / 2
            # Check within axis bounds (allow slight margin)
            if box_t_lo < log_t_min - 0.1 or box_t_hi > log_t_max + 0.1:
                continue
            if box_m_lo < 10 or box_m_hi > 26.5:
                continue
            # Check overlap
            overlap = False
            for (pt_lo, pt_hi, pm_lo, pm_hi) in placed_boxes:
                if (box_t_lo < pt_hi and box_t_hi > pt_lo and
                        box_m_lo < pm_hi and box_m_hi > pm_lo):
                    overlap = True
                    break
            if not overlap:
                best_pos = (lc_t, lc_m)
                placed_boxes.append((box_t_lo, box_t_hi, box_m_lo, box_m_hi))
                break

        if best_pos is None:
            continue

        label_t = 10 ** best_pos[0]
        label_m = best_pos[1]

        ax.annotate(
            name,
            xy=(t, m),
            xytext=(label_t, label_m),
            textcoords="data",
            fontsize=8, color=color, fontweight="bold",
            ha="center", va="center",
            arrowprops=dict(arrowstyle="->", color=color, lw=0.7,
                            shrinkA=2, shrinkB=4,
                            connectionstyle="arc3,rad=0.0"),
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color,
                      alpha=0.9, lw=0.5),
            zorder=25,
        )
        placed_count += 1


def plot_density(t_bg, mag_bg, svom_t, svom_mag, svom_names,
                 ul_t, ul_mag, ul_names, ul_auto, band_label, out_name):
    """Plot density distribution with SVOM overlay."""
    fig, ax = plt.subplots(figsize=(16, 10))

    # ---- 1. Background: 2D density histogram ----
    t_bins = np.logspace(0, 7, 80)
    m_bins = np.linspace(8, 26, 90)
    H, _, _ = np.histogram2d(t_bg, mag_bg, bins=[t_bins, m_bins])

    pcm = ax.pcolormesh(t_bins, m_bins, H.T, cmap="Greys",
                        norm=LogNorm(vmin=1, vmax=max(H.max(), 2)),
                        shading="auto")
    cbar = fig.colorbar(pcm, ax=ax, pad=0.02, shrink=0.8)
    cbar.set_label(f"GRB sample density ({band_label} band)", fontsize=14)
    cbar.ax.tick_params(labelsize=11)

    # ---- 2. SVOM VT_R detections ----
    if len(svom_t) > 0:
        ax.scatter(svom_t, svom_mag, c="red", s=140, zorder=10,
                   edgecolors="darkred", linewidths=1.4,
                   label=f"SVOM/VT VT_R detection (n={len(svom_t)})", alpha=0.9)

    # ---- 3. SVOM VT_R upper limits ----
    if len(ul_t) > 0:
        ax.scatter(ul_t, ul_mag, marker="v", c="lime", s=120, zorder=10,
                   edgecolors="darkgreen", linewidths=1.2,
                   label=f"SVOM/VT VT_R upper limit (n={len(ul_t)})", alpha=0.9)

    # ---- 4. Label SVOM GRBs (detections - no labels) ----

    # ---- 5. Label SVOM GRBs (upper limits - auto followup only, placed below 24 mag) ----
    ul_points = []
    if len(ul_t) > 0 and len(ul_names) > 0:
        ul_unique = {}
        for t, m, n, af in zip(ul_t, ul_mag, ul_names, ul_auto):
            # Only label auto followup upper limits
            if not af:
                continue
            if n and (n not in ul_unique or m < ul_unique[n][1]):
                ul_unique[n] = (t, m)
        for name, (t, m) in ul_unique.items():
            ul_points.append((t, m, name))
    _place_labels_below(ax, ul_points, "green", max_labels=30)

    # ---- 6. Axes ----
    ax.set_xscale("log")
    ax.set_xlim(50, 1e6)
    ax.set_ylim(26.5, 10)
    ax.set_xlabel("Time after trigger (s)", fontsize=15)
    ax.set_ylabel("Magnitude", fontsize=15)
    ax.set_title(
        f"GRB Light Curve Density ({band_label} band, grey) "
        f"vs SVOM/VT VT_R (red)",
        fontsize=16, fontweight="bold", pad=12,
    )
    ax.tick_params(axis="both", labelsize=12)
    ax.grid(True, which="both", alpha=0.2)
    ax.legend(loc="upper right", fontsize=12, framealpha=0.9)

    plt.tight_layout()
    out_path = os.path.join(OUT_DIR, out_name)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    print(f"[OK] Saved: {out_path}")
    plt.close(fig)


def main():
    print("=" * 60)
    print("GRB Light Curve Density + SVOM/VT VT_R")
    print("=" * 60)

    # Load SVOM VT_R
    print("\n[1] Loading SVOM/VT VT_R data...")
    svom_t, svom_mag, svom_names, ul_t, ul_mag, ul_names, ul_auto = load_svom_vt_r()
    print(f"    VT_R detections: {len(svom_t)}")
    print(f"    VT_R upper limits: {len(ul_t)} (auto followup: {sum(1 for a in ul_auto if a)})")

    # Plot 1: R-band background
    print("\n[2] Loading Swift R-band sample...")
    rt, rm, _, rnames, _ = load_swift_bands(R_BANDS)
    print(f"    R-band points: {len(rt)}")
    plot_density(rt, rm, svom_t, svom_mag, svom_names, ul_t, ul_mag, ul_names, ul_auto,
                 "R", "lc_density_vs_vt.png")

    # Plot 2: i/z band background
    print("\n[3] Loading Swift i/z-band sample...")
    it, im, _, inames, _ = load_swift_bands(IZ_BANDS)
    print(f"    i/z-band points: {len(it)}")
    plot_density(it, im, svom_t, svom_mag, svom_names, ul_t, ul_mag, ul_names, ul_auto,
                 "i/z", "lc_density_iz_vs_vt.png")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
