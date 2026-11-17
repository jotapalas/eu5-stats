# User guide

The web interface shows how every country in our multiplayer campaigns develops over time. It is built
from the saves uploaded after each session. The interface is in Spanish, and the names below match what
you see on screen.

The public site is read-only. Uploading saves and changing settings only happen on the organiser's
machine, so new sessions appear once the organiser publishes again.

## Campaigns

The start page lists the campaigns. Open one to see its tabs:

| Tab | What it shows |
|---|---|
| **Ranking** | The latest values of every country in one table |
| **Comparativa** | One metric over time for the countries you pick |
| **Sesiones** | Each play session and what changed during it |
| **Ajustes** | Organiser only: tracked countries, main players, rename/delete |

Every metric is explained in [metrics.md](metrics.md). Hovering a column or chart title also shows a short
English description.

## Ranking

One row per country with its most recent values. It is sorted by score position by default.

- Click a column header to sort by it. Click again to reverse.
- **Todas / Economía / Tamaño y poder / Militar / Estado** filters the columns by category.
- **Sólo jugadores** hides AI countries.
- A date in amber next to a country means it is missing from the latest save (annexed, or it changed
  into something not tracked). Its last known values are shown.
- Click a row to open the country sheet.

## Comparativa

Pick a **Métrica** and tick the **Países** to draw. Hovering a country in the list highlights its line.
The URL keeps your choice, so you can share the link.

- The horizontal axis is the in-game date. With per-save metrics there is one point per uploaded save.
- **Population, tax base and economic base** use the yearly record the game keeps itself. These lines
  start before the first uploaded save, often at the campaign start.
- **Rank metrics** (score position, great power rank) are drawn upside down on a logarithmic scale, so
  1st place is at the top and the differences among the leaders are visible.
- Each country keeps the same colour everywhere. There are 8 colours: countries 9–16 reuse them with a
  dashed line, and the rest are grey.

## Country sheet (Ficha de país)

A small chart for every metric of one country, grouped by category. It also shows:

- the in-game dates covered and the number of saves,
- every player who controlled it in the saves,
- its tag changes (e.g. `ENG (desde 1367.1.1) → GBR (desde 1520.3.1)`). A country that forms a new
  nation keeps a single history.

The number next to each value is the change since the first save. It is green when the change is good
and red when it is bad. For inflation, war exhaustion and ranks, a decrease is good. Click a small chart
to open it in Comparativa. **Comparar con otros** does the same with the country preselected.

## Sesiones

The list of sessions with the real date they were played, the in-game dates they cover and their saves.
Open one to see:

- its saves and their status (**En cola**, **Procesando**, **Procesado**, **Error**, **Duplicada**),
- a table with every country's value at the start and end of the session and the change.

## Who counts as a "country"

Statistics belong to countries, not players. Several people may play the same country over a campaign,
and a country can go from human to AI and back. A country's label shows its current tag and its players
(or **IA**). The organiser can set a main player name per country.

All countries played by a human are included. The organiser can also add AI countries (for example a
rival) in **Ajustes**.
