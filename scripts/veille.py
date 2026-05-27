import os
import re
import sys
import requests
from datetime import datetime
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "36de32c9-5992-8114-91b7-d0475047c3af")

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]

SEARCH_QUERIES = [
    "Instagram algorithm 2026 Reels trends this week",
    "motion design trends 2026 Instagram creators",
    "video editing content creators Instagram growth strategy 2026",
    "best performing Reels formats 2026 engagement",
    "Instagram creator economy news this week",
]


def tavily_search(query: str) -> str:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            timeout=15,
        )
        data = resp.json()
        results = data.get("results", [])
        lines = []
        for r in results:
            content = r.get("content", "")[:250]
            lines.append(f"- [{r['title']}]({r['url']}): {content}")
        return "\n".join(lines) if lines else "Aucun résultat."
    except Exception as e:
        return f"Erreur: {e}"


def generate_veille() -> tuple[str, str]:
    today = datetime.now()
    date_long = f"{today.day} {MONTHS_FR[today.month - 1]} {today.year}"
    date_short = today.strftime("%d/%m/%y")

    print("🔎 Recherches web en cours...")
    search_context = ""
    for query in SEARCH_QUERIES:
        print(f"  → {query}")
        result = tavily_search(query)
        search_context += f"\n\n**Recherche : {query}**\n{result}"

    prompt = f"""Tu es un assistant de veille stratégique pour @alex.editspr, créateur de contenu spécialisé en motion design & vidéo editing sur Instagram (clients = entrepreneurs/créateurs, personal brand).

Voici les résultats de recherche web actuels :{search_context}

---

En te basant UNIQUEMENT sur ces résultats de recherche (n'invente aucun chiffre ni fait), rédige la veille hebdomadaire complète en français pour le {date_long}.

Cite les sources avec le format [Nom du Site](URL) après chaque information.

Utilise EXACTEMENT ce template (titres avec emojis obligatoires) :

# 🔍 Veille Instagram — {date_long}
@alex.editspr · Motion Design & Vidéo Editing

## ⭐ Action prioritaire de la semaine
[1 seule action concrète et immédiatement actionnable pour cette semaine]

## 📊 Tendances macro Instagram
[3-4 paragraphes sur les grandes évolutions algo. Sources.]

## 🎯 Niche Vidéo Editing / Motion Design
[3-4 paragraphes sur les tendances spécifiques à la niche. Sources.]

## 🔥 Formats Reels chauds en ce moment
[3 formats qui fonctionnent avec angle adapté pour @alex.editspr. Sources.]

## ⚡ Signaux algo à surveiller
[3 points techniques avec comportements concrets à adopter. Sources.]

## 🕵️ Compétiteurs & opportunités
[2 observations sur la niche + 1 opportunité sous-exploitée pour Alex.]

## 🧠 Insight conversion
[2 paragraphes sur comment transformer la visibilité en clients ou abonnés fidèles.]

## 📈 Métriques cibles cette semaine
| Métrique | Objectif |
|---|---|
| Taux de complétion | > 70% |
| Visites de profil post-Reel | > 5% des vues |
| Saves (enregistrements) | > 2% des vues |
| Réponses dans les 30 min | 100% des commentaires |

## 💡 5 idées de contenu pour @alex.editspr
1. "Titre accrocheur" — Format + durée + angle stratégique
2. "Titre accrocheur" — Format + durée + angle stratégique
3. "Titre accrocheur" — Format + durée + angle stratégique
4. "Titre accrocheur" — Format + durée + angle stratégique
5. "Titre accrocheur" — Format + durée + angle stratégique

## 📅 Plan suggéré cette semaine
Lun : [action] · Mer : [action] · Ven : [action] · Dim : [action ou off]
"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("🤖 Génération du contenu avec Claude...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text, date_short


# ── Notion helpers ──────────────────────────────────────────────────────────

def parse_rich_text(text: str) -> list:
    """Convert inline markdown (links, bold) to Notion rich_text array."""
    parts = []
    pattern = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)|\*\*([^\*]+)\*\*')
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            parts.append({"type": "text", "text": {"content": text[pos:m.start()]}})
        if m.group(2):  # link
            parts.append({
                "type": "text",
                "text": {"content": m.group(1), "link": {"url": m.group(2)}},
            })
        else:  # bold
            parts.append({
                "type": "text",
                "text": {"content": m.group(3)},
                "annotations": {"bold": True},
            })
        pos = m.end()
    if pos < len(text):
        parts.append({"type": "text", "text": {"content": text[pos:]}})
    return parts or [{"type": "text", "text": {"content": text}}]


def create_table_block(rows: list) -> dict:
    if not rows:
        return {}
    width = max(len(r) for r in rows)
    notion_rows = []
    for row in rows:
        cells = [[{"type": "text", "text": {"content": c}}] for c in row]
        while len(cells) < width:
            cells.append([{"type": "text", "text": {"content": ""}}])
        notion_rows.append({"object": "block", "type": "table_row", "table_row": {"cells": cells}})
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": notion_rows,
        },
    }


def markdown_to_notion_blocks(text: str) -> list:
    blocks = []
    table_rows: list[list[str]] = []
    in_table = False

    for line in text.split("\n"):
        stripped = line.strip()

        # Flush table if we leave it
        if in_table and not (stripped.startswith("|") and stripped.endswith("|")):
            if table_rows:
                blocks.append(create_table_block(table_rows))
            table_rows = []
            in_table = False

        if stripped == "":
            continue

        if stripped.startswith("# "):  # H1 — skip (becomes page title)
            continue

        if stripped.startswith("## "):  # H2 → heading_2
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]},
            })
            continue

        if stripped.startswith("|") and stripped.endswith("|"):  # table row
            if re.fullmatch(r'[\|\s\-]+', stripped):  # separator
                continue
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            table_rows.append(cells)
            in_table = True
            continue

        if re.match(r'^\d+\.', stripped):  # numbered list
            content = re.sub(r'^\d+\.\s*', '', stripped)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": parse_rich_text(content)},
            })
            continue

        if stripped.startswith("- "):  # bullet list
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_rich_text(stripped[2:])},
            })
            continue

        # Regular paragraph
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": parse_rich_text(stripped)},
        })

    if in_table and table_rows:
        blocks.append(create_table_block(table_rows))

    return blocks


def create_notion_page(title: str, blocks: list) -> str:
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": blocks[:100],
    }
    resp = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]
    page_url = page["url"]

    remaining = blocks[100:]
    for i in range(0, len(remaining), 100):
        batch = remaining[i : i + 100]
        requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            json={"children": batch},
        ).raise_for_status()

    return page_url


def main():
    veille_text, date_short = generate_veille()
    print("✅ Contenu généré")

    blocks = markdown_to_notion_blocks(veille_text)
    print(f"📦 {len(blocks)} blocs Notion créés")

    title = f"Veille du {date_short}"
    url = create_notion_page(title, blocks)
    print(f"✅ Page Notion créée : {url}")


if __name__ == "__main__":
    main()
