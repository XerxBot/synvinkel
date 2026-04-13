"""
Visualiserar politiska förflyttningar: deklarerad → revealed position.
Sparar en PNG-fil med GAL-TAN (Y) × Vänster-Höger (X) koordinatsystem.
"""
import asyncio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from sqlalchemy import select, and_
from app.database import AsyncSessionLocal as async_session
from app.models.organization import SourcePerson

LEANING_SCALE = {
    "far-left": -3, "left": -2, "center-left": -1,
    "center": 0,
    "center-right": 1, "right": 2, "far-right": 3,
}
GAL_TAN_SCALE = {
    "gal": -2, "center-gal": -1, "center": 0, "center-tan": 1, "tan": 2,
}


def to_xy(leaning, gal_tan):
    x = LEANING_SCALE.get(leaning or "", None)
    y = GAL_TAN_SCALE.get(gal_tan or "", None)
    return x, y


def movement_magnitude(dx, dy):
    if dx is None or dy is None:
        return 0
    return (dx**2 + dy**2) ** 0.5


async def get_persons():
    async with async_session() as session:
        result = await session.execute(
            select(SourcePerson).where(
                SourcePerson.revealed_political_leaning.isnot(None)
            )
        )
        return result.scalars().all()


async def main():
    persons = await get_persons()
    print(f"Hittade {len(persons)} analyserade personer")

    rows = []
    for p in persons:
        x_dec, y_dec = to_xy(p.political_leaning, p.gal_tan_position)
        x_rev, y_rev = to_xy(p.revealed_political_leaning, p.revealed_gal_tan_position)
        if x_dec is None or x_rev is None:
            continue
        dx = x_rev - x_dec
        dy = (y_rev or 0) - (y_dec or 0)
        mag = movement_magnitude(dx, dy)
        rows.append({
            "name": p.name,
            "x_dec": x_dec, "y_dec": y_dec or 0,
            "x_rev": x_rev, "y_rev": y_rev or 0,
            "dx": dx, "dy": dy, "mag": mag,
            "discrepancy": p.leaning_discrepancy or "none",
        })

    rows.sort(key=lambda r: r["mag"], reverse=True)
    for r in rows:
        print(f"  {r['name']:35} {r['discrepancy']:12} mag={r['mag']:.2f}  "
              f"({r['x_dec']:.0f},{r['y_dec']:.0f}) → ({r['x_rev']:.0f},{r['y_rev']:.0f})")

    # Välj top-movers + alla med moderate/significant
    top = [r for r in rows if r["discrepancy"] in ("significant", "moderate")]
    top += [r for r in rows if r not in top and r["mag"] > 0.5]
    top = sorted(top, key=lambda r: r["mag"], reverse=True)[:20]
    all_shown = rows  # visa alla som bakgrund

    fig, ax = plt.subplots(figsize=(14, 10))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#0f1117")

    # Rutnät och axlar
    for x in range(-3, 4):
        ax.axvline(x, color="#2a2a3a", linewidth=0.4, zorder=0)
    for y in range(-2, 3):
        ax.axhline(y, color="#2a2a3a", linewidth=0.4, zorder=0)
    ax.axvline(0, color="#444466", linewidth=0.8, zorder=1)
    ax.axhline(0, color="#444466", linewidth=0.8, zorder=1)

    # Bakgrundsfärger per kvadrant
    ax.fill_between([-3.5, 0], [-2.5, -2.5], [2.5, 2.5], alpha=0.05, color="#4488ff", zorder=0)
    ax.fill_between([0, 3.5],  [-2.5, -2.5], [2.5, 2.5], alpha=0.05, color="#ff4444", zorder=0)

    # Rita alla personer som diskreta bakgrundspunkter
    for r in all_shown:
        if r not in top:
            ax.plot(r["x_dec"], r["y_dec"], "o", color="#444466", markersize=4, alpha=0.5, zorder=2)
            ax.plot(r["x_rev"], r["y_rev"], "s", color="#664466", markersize=4, alpha=0.5, zorder=2)

    # Rita top-movers med pilar
    cmap = plt.cm.plasma
    max_mag = max((r["mag"] for r in top), default=1)

    for r in top:
        color = cmap(r["mag"] / max_mag * 0.85 + 0.1)
        xd, yd = r["x_dec"], r["y_dec"]
        xr, yr = r["x_rev"], r["y_rev"]

        # Deklarerad position
        ax.plot(xd, yd, "o", color="#aaaacc", markersize=7, zorder=4)
        # Revealed position
        ax.plot(xr, yr, "D", color=color, markersize=8, zorder=5)

        if r["mag"] > 0.01:
            ax.annotate(
                "",
                xy=(xr, yr), xytext=(xd, yd),
                arrowprops=dict(
                    arrowstyle="->",
                    color=color,
                    lw=1.8,
                    connectionstyle="arc3,rad=0.15",
                ),
                zorder=3,
            )

        # Etikett vid revealed-position
        offset_x = 0.08 + (0.05 if xr > xd else -0.05)
        offset_y = 0.12
        short_name = r["name"].split()[-1]  # efternamn
        ax.text(
            xr + offset_x, yr + offset_y,
            short_name,
            color="#ddddee",
            fontsize=7.5,
            fontweight="bold" if r["discrepancy"] == "significant" else "normal",
            zorder=6,
        )

    # Axel-etiketter
    ax.set_xlim(-3.7, 3.7)
    ax.set_ylim(-2.6, 2.6)
    ax.set_xticks(range(-3, 4))
    ax.set_xticklabels(
        ["Långt\nvänster", "Vänster", "Center-\nvänster", "Center",
         "Center-\nhöger", "Höger", "Långt\nhöger"],
        color="#aaaacc", fontsize=8
    )
    ax.set_yticks(range(-2, 3))
    ax.set_yticklabels(["GAL", "Center-GAL", "Center", "Center-TAN", "TAN"],
                        color="#aaaacc", fontsize=8)
    ax.tick_params(colors="#555577")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")

    ax.set_xlabel("Vänster ←  Ekonomisk/Politisk position  → Höger",
                  color="#8888aa", fontsize=10, labelpad=10)
    ax.set_ylabel("GAL ↑  Kulturell position  ↓ TAN",
                  color="#8888aa", fontsize=10, labelpad=10)
    ax.set_title(
        "Politisk förflyttning: Deklarerad → Revealed position\n"
        "● = deklarerad  ◆ = revealed  pil = förflyttning  (färg = magnitud)",
        color="#ccccee", fontsize=12, pad=15
    )

    # Legend
    legend_elements = [
        mpatches.Patch(color="#aaaacc", label="Deklarerad position (●)"),
        mpatches.Patch(color=cmap(0.9), label="Revealed position (◆) — hög magnitud"),
        mpatches.Patch(color=cmap(0.3), label="Revealed position (◆) — låg magnitud"),
    ]
    ax.legend(handles=legend_elements, facecolor="#1a1a2e", edgecolor="#333355",
              labelcolor="#ccccee", fontsize=8, loc="lower right")

    # Diskrepansstämplar
    sig_names = [r["name"].split()[-1] for r in top if r["discrepancy"] == "significant"]
    if sig_names:
        ax.text(3.6, 2.5, f"Signifikant: {', '.join(sig_names)}",
                ha="right", va="top", color="#ff9944", fontsize=7, style="italic")

    plt.tight_layout()
    out = "/app/political_movements.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nSparad: {out}")


asyncio.run(main())
