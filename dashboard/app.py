#!/usr/bin/env python3
"""
Leaf Literature Agent — live Streamlit dashboard.

Reads db/leaf_lit.db directly (never a stale snapshot). Run with:

    streamlit run dashboard/app.py

Tabs: Overview · Corpus · AI / ML methods · Topic coverage.
The "AI / ML methods" tab surfaces papers whose reported method is a machine-
learning / deep-learning / digital-twin / DOE-RSM / proteomics approach — in leaf
protein OR in analogous food systems whose method transfers to leaf-protein
purification (each card states the transfer logic).

NOTE (OneDrive sync): .py files do not sync via OneDrive — zip this for transport
(see /pack). The DB it reads (db/leaf_lit.db) does sync natively.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "leaf_lit.db")

# ── palette: quiet work-focused light UI ──────────────────────────────────────
ACCENT = "#167a55"
CYAN = "#2563eb"
AMBER = "#b7791f"
INK = "#17231d"
INK2 = "#5f6f66"
SURFACE = "#ffffff"
CANVAS = "#f7faf7"
RING = "#d9e3dc"

st.set_page_config(page_title="Leaf Literature Agent", page_icon="🌿", layout="wide")

# ── copy ──────────────────────────────────────────────────────────────────────
T = {'title': 'Leaf Literature Agent',
 'tagline': 'A live, queryable knowledge base on leaf-protein extraction and the removal of '
            'off-odor, off-flavor and green color — LOX mechanism at its core.',
 'phase': 'Phase 1 · seed corpus · SQLite live',
 'refresh': '↻ Refresh from DB',
 'k_papers': 'Papers',
 'k_numeric': 'Numeric results',
 'k_flag': 'Need verification',
 'k_species': 'Species',
 'k_full': 'Full-text / +SI',
 'k_ai': 'AI / ML papers',
 'k_extracted': 'Extracted (unverified)',
 'k_extracted_help': 'Numeric values auto-extracted from PDFs by Claude (Bedrock). Every value '
                     'carries a verbatim source quote; NOT yet human-verified.',
 'tab_overview': 'Overview',
 'tab_corpus': 'Corpus',
 'tab_ai': 'AI / ML methods',
 'tab_extracted': 'Extracted data',
 'tab_cats': 'Topic coverage',
 'ex_h': 'LLM-extracted numeric results',
 'ex_warn': '⚠ UNVERIFIED — auto-extracted by Claude from the source PDFs and awaiting human '
            'spot-check. The curated seed values (Overview tab) are the reference; these are the '
            'full harvest, every value traceable to a verbatim quote.',
 'ex_n': 'Each row is one numeric value the model found in a paper, with its verbatim source '
         'location. Filter, then verify against the PDF using the quote.',
 'ex_search': 'Search quantity / paper / quote',
 'ex_paper': 'Paper',
 'ex_only_flag': 'only ⚠ needs-verify',
 'note_purity': "⚑ What 'purity %' means here: it is the protein CONTENT of the powder — one axis "
                "only. The project's real target is a CLEAN POWDER — minimum off-odor, off-flavor, "
                'and green color. Those sensory & color goals matter more than protein % alone; '
                'track their (sparse) coverage in the Gaps & target tab.',
 'tab_normalize': 'Cross-study',
 'tab_verify': 'Verify',
 'tab_gaps': 'Gaps & target',
 'tab_compare': 'Compare / query',
 'norm_h': 'Cross-study comparison (normalization)',
 'norm_n': 'Pick a measured quantity → every value for it across all studies, aligned to one unit '
           "so they are comparable — the 'learnable matrix'. Seed = curated; extracted = auto "
           '(unverified).',
 'norm_pick': 'Quantity',
 'norm_unit': 'Units seen',
 'norm_learnable': 'studies covering this quantity',
 'ver_h': 'Verification workbench',
 'ver_n': 'The action path for flagged values. Edit a value in place, tick ✓ verified, add a note '
          '— then Save writes back to db/leaf_lit.db. This is how the AI-built numbers become '
          'human-verified gold.',
 'ver_scope': 'Show',
 'ver_flagged': 'only needs-verify / unverified',
 'ver_all': 'all',
 'ver_save': '💾 Save changes to DB',
 'ver_saved': 'Saved. Reloading…',
 'ver_none': 'Nothing to verify with the current filter.',
 'gaps_h': 'Coverage & gaps — including the real (sensory) target',
 'gaps_n': 'Where is the corpus thin? Rows = species, columns = outcome. Empty / low cells are '
           'gaps to fill. The sensory/color columns (off_odor, off_flavor, color) are the '
           "project's actual goal — and are visibly the least covered.",
 'gaps_sensory': 'Sensory & color target coverage (the real goal, not protein %)',
 'cmp_h': 'Compare studies',
 'cmp_pick': 'Pick 2–4 papers to compare',
 'cmp_n': 'Line up methods and numbers side by side.',
 'qry_h': 'Query the numeric matrix',
 'qry_n': 'Build a filtered, analysable table across all studies — then download it.',
 'qry_prov': 'Source',
 'qry_dl': '⬇ Download CSV',
 'ver_how': '**How to verify — you are confirming numbers the AI already extracted, not hunting '
            'for missing data:** ① note the **paper**; ② read the **source (verbatim)** column — '
            "it quotes the exact table / section the number came from; ③ open that paper's PDF and "
            'find it; ④ if correct, tick **✓ verified**; if wrong, type the **corrected value** + '
            'a note; ⑤ press **Save**.',
 'ver_pdf': 'PDF to open',
 'norm_sensory_only': '👃 only sensory / colour parameters (the real target)',
 'norm_none': 'No parameter matches. Uncheck the sensory filter.',
 'norm_is_sensory': "sensory / colour — the project's real target",
 'norm_thin': '⚠ Only one study reports this — too thin for a cross-study comparison yet (this is '
              'exactly the kind of gap the Gaps tab surfaces).',
 'ro_banner': '🔒 Read-only shared view. Browsing, charts, and CSV export work; editing & '
              'verification happen on the local instance (to protect the data).',
 'purity_h': 'Protein purity across the corpus',
 'purity_n': "Each bar is one study's best reported purity. Amber = parsed from a narrative note, "
             'flagged for human verification (never trusted blindly).',
 'yield_h': 'Extraction yield across the corpus',
 'yield_n': 'The purity–yield trade-off is visible: the purest routes rarely give the highest '
            'yield.',
 'filters': 'Filters',
 'f_species': 'Species',
 'f_rel': 'Relevance',
 'f_flag': 'Only papers with a needs-verify value',
 'f_search': 'Search title / species / method',
 'showing': 'Showing',
 'of': 'of',
 'papers': 'papers',
 'story': 'Scientific story',
 'findings': 'Findings',
 'tags': 'Topic tags',
 'open': 'open details',
 'ai_intro': 'Papers whose **reported method is a machine-learning, deep-learning, digital-twin, '
             'or statistical-optimization approach** — in leaf protein or in an analogous food '
             'system whose method transfers to leaf-protein purification. Each card states the '
             'transfer logic (why an off-topic system still informs this project).',
 'ai_core': 'Machine learning · deep learning · digital twins',
 'ai_core_n': 'The AI-sensing / AI-modeling precedents. None are about leaf protein — they prove '
              'the *method* works in a comparable food problem.',
 'ai_other': 'Other computational methods (optimization · proteomics)',
 'ai_other_n': 'Statistical process optimization (DOE / RSM) and proteomic characterization — '
               'computational, but not AI-sensing precedents.',
 'technique': 'Technique',
 'system': 'System (not leaf protein)',
 'transfer': 'Why it transfers',
 'no_rows': 'No papers match these filters.',
 'cats_h': 'Topic coverage',
 'cats_n': 'The controlled vocabulary that makes the corpus queryable.',
 'prov': 'Every number traces to a paper_id · nothing fabricated · null ≠ zero',
 'reported': 'reported value',
 'needs': 'needs verify'}
TECH_LABEL = {
    "deep_learning": "Deep learning", "ML": "Machine learning", "digital_twin": "Digital twin",
    "DOE_RSM": "DOE / RSM", "proteomics": "Proteomics",
}

# Read-only mode for the shared/deployed instance: no DB writes (verification is
# done on the local instance). Set env LEAF_READONLY=1 on Streamlit Cloud.
READ_ONLY = os.environ.get("LEAF_READONLY", "").lower() in ("1", "true", "yes")

# Human-readable names for the controlled quantities (the raw keys are terse).
QUANTITY_LABEL = {
    "protein_purity_pct": "Protein content %  (how pure)",
    "yield_pct": "Yield %  (how much protein recovered)",
    "chlorophyll_removal_pct": "Chlorophyll removal %  (colour)",
    "rubisco_specificity_pct": "RuBisCO specificity %",
    "chlorophyll_content": "Chlorophyll content  (colour)",
    "sensory_offodor_score": "Off-odor score  (aroma)",
    "sensory_offflavor_score": "Off-flavor score  (taste)",
    "total_C6_aldehydes": "Total C6 aldehydes  (green aroma)",
    "hexanal_conc": "Hexanal  (grassy aroma)",
    "color_L": "Colour L*  (lightness)", "color_a": "Colour a*  (green–red)",
    "color_b": "Colour b*  (blue–yellow)", "LOX_activity": "LOX activity",
    "model_r2_solubility": "Model R2 — solubility prediction",
    "model_r2_emulsifying_activity_index": "Model R2 — emulsifying activity prediction",
    "model_r2_emulsifying_capacity": "Model R2 — emulsifying capacity prediction",
    "model_r2_gel_strength": "Model R2 — gel strength prediction",
    "model_rmse_solubility": "Model RMSE — solubility prediction",
    "model_rmse_emulsifying_activity_index": "Model RMSE — emulsifying activity prediction",
    "model_rmse_emulsifying_capacity": "Model RMSE — emulsifying capacity prediction",
    "model_rmse_gel_strength": "Model RMSE — gel strength prediction",
    "dataset_n_points": "Dataset size  (data points)",
}
# quantities that speak to the REAL target — off-odor / off-flavor / colour
_SENSORY_KW = ("odor", "odour", "flavor", "flavour", "aldehyde", "hexanal", "hexenal",
               "voc", "sensory", "aroma", "chlorophyll", "color", "colour", "green", "lox")


def q_friendly(q: str) -> str:
    return QUANTITY_LABEL.get(q, (q or "").replace("_", " "))


def q_is_sensory(q: str) -> bool:
    ql = (q or "").lower()
    return any(k in ql for k in _SENSORY_KW)


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


# ── data ──────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load(_mtime: float):
    con = sqlite3.connect(DB_PATH)
    papers = pd.read_sql_query("SELECT * FROM papers", con)
    numeric = pd.read_sql_query("SELECT * FROM numeric_results", con)
    cats = pd.read_sql_query("SELECT * FROM paper_categories", con)
    con.close()

    papers["year"] = pd.to_numeric(papers["year"], errors="coerce").astype("Int64")

    def cats_of(pid):
        return cats.loc[cats.paper_id == pid, "category"].tolist()

    papers["cats"] = papers.paper_id.map(cats_of)
    papers["species"] = papers.cats.map(
        lambda cs: next((c.split(":", 1)[1] for c in cs if c.startswith("species:")), "other"))
    papers["analysis"] = papers.cats.map(
        lambda cs: [c.split(":", 1)[1] for c in cs if c.startswith("analysis:")])

    if "provenance" not in numeric.columns:
        numeric["provenance"] = "seed"
    # headline purity/yield come from the curated SEED rows (one per paper), so the
    # overview charts stay clean; the many llm-extracted rows populate the Extracted tab.
    seed_num = numeric[numeric.provenance == "seed"]
    pv = seed_num[seed_num.quantity == "protein_purity_pct"].drop_duplicates("paper_id").set_index("paper_id")
    yv = seed_num[seed_num.quantity == "yield_pct"].drop_duplicates("paper_id").set_index("paper_id")
    papers["purity"] = papers.paper_id.map(pv["value"])
    papers["purity_flag"] = papers.paper_id.map(pv["needs_human"]).fillna(0).astype(int)
    papers["yield"] = papers.paper_id.map(yv["value"])
    papers["yield_flag"] = papers.paper_id.map(yv["needs_human"]).fillna(0).astype(int)
    # NB: do NOT name this column "flags" — it collides with the reserved pandas
    # DataFrame/Series `.flags` attribute, so attribute access returns the wrong thing.
    papers["n_flags"] = papers.paper_id.map(
        seed_num[seed_num.needs_human == 1].groupby("paper_id").size()).fillna(0).astype(int)
    papers["n_extracted"] = papers.paper_id.map(
        numeric[numeric.provenance.str.startswith("llm:")].groupby("paper_id").size()
    ).fillna(0).astype(int)
    papers["year_str"] = papers["year"].map(lambda y: "" if pd.isna(y) else str(int(y)))
    return papers, numeric, cats


def ensure_cols():
    """Add verification columns to numeric_results if missing (one-time migration)."""
    con = sqlite3.connect(DB_PATH)
    have = [r[1] for r in con.execute("PRAGMA table_info(numeric_results)")]
    for name, ddl in [("provenance", "TEXT DEFAULT 'seed'"), ("verified", "INTEGER DEFAULT 0"),
                      ("verified_value", "REAL"), ("verified_note", "TEXT"), ("verified_date", "TEXT")]:
        if name not in have:
            con.execute(f"ALTER TABLE numeric_results ADD COLUMN {name} {ddl}")
    con.commit()
    con.close()


ensure_cols()
mtime = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0.0
papers, numeric, cats = load(mtime)

# ── global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  .stApp {{background:{CANVAS}}}
  header[data-testid="stHeader"] {{background:{CANVAS};box-shadow:0 1px 0 {RING}}}
  .block-container {{padding-top:4.4rem;max-width:1400px}}
  h1,h2,h3 {{letter-spacing:-.01em}}
  .llead {{color:{INK2};font-size:.95rem;max-width:70ch}}
  .eyebrow {{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;letter-spacing:.18em;
     text-transform:uppercase;color:{AMBER};margin-bottom:.35rem}}
  div[data-testid="stMetric"] {{background:{SURFACE};border:1px solid {RING};border-radius:14px;
     padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04)}}
  div[data-testid="stMetricValue"] {{font-variant-numeric:tabular-nums}}
  .chip {{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:.68rem;
     padding:2px 9px;border-radius:999px;border:1px solid {RING};color:{INK2};margin:2px 4px 2px 0}}
  .chip.tech {{color:{ACCENT};border-color:{ACCENT}}}
  .chip.sys {{color:{CYAN};border-color:{CYAN}}}
  .aicard {{background:{SURFACE};border:1px solid {RING};border-left:3px solid {ACCENT};
     border-radius:12px;padding:14px 18px;margin-bottom:10px}}
  .transfer {{color:{INK};font-size:.9rem;border-left:2px solid {AMBER};padding-left:12px;margin-top:8px}}
  .foot {{color:{INK2};font-family:ui-monospace,Menlo,monospace;font-size:.75rem;
     border-top:1px solid {RING};margin-top:2rem;padding-top:1rem}}
</style>
""", unsafe_allow_html=True)

# ── sidebar: refresh ──────────────────────────────────────────────────────────
t = T
with st.sidebar:
    st.markdown("### Leaf Literature Agent")
    if st.button(t["refresh"], width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(t["phase"])
    st.caption(f"db/leaf_lit.db · {len(papers)} {t['k_papers'].lower()}")
    if READ_ONLY:
        st.caption("🔒 read-only shared view")


# ── header ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="eyebrow">Leaf Protein · Literature Intelligence</div>', unsafe_allow_html=True)
st.markdown(f"# {t['title']}")
st.markdown(f'<p class="llead">{t["tagline"]}</p>', unsafe_allow_html=True)

seed_num = numeric[numeric.provenance == "seed"]
llm_num = numeric[numeric.provenance.str.startswith("llm:")]
n_flag = int((seed_num.needs_human == 1).sum())
n_full = int(papers.verification_level.fillna("").str.contains("full_text").sum())
n_ai = int(papers.analysis.map(lambda a: any(x in a for x in ("ML", "deep_learning", "digital_twin"))).sum())

c = st.columns(7)
c[0].metric(t["k_papers"], len(papers))
c[1].metric(t["k_numeric"], len(seed_num))
c[2].metric(t["k_flag"], n_flag)
c[3].metric(t["k_species"], papers.species.nunique())
c[4].metric(t["k_full"], n_full)
c[5].metric(t["k_ai"], n_ai)
c[6].metric(t["k_extracted"], len(llm_num), help=t["k_extracted_help"])

(tab_ov, tab_corpus, tab_ex, tab_norm, tab_verify, tab_gaps,
 tab_compare, tab_ai, tab_cats) = st.tabs(
    [t["tab_overview"], t["tab_corpus"], t["tab_extracted"], t["tab_normalize"],
     t["tab_verify"], t["tab_gaps"], t["tab_compare"], t["tab_ai"], t["tab_cats"]])


# ── charts helper ─────────────────────────────────────────────────────────────
def bar_chart(df, quantity, title):
    d = df[df.quantity == quantity].copy()
    d["status"] = d.needs_human.map({0: t["reported"], 1: t["needs"]})
    d["src"] = d.source_location.str.slice(0, 160)
    chart = (
        alt.Chart(d)
        .mark_bar(cornerRadiusEnd=4, height=16)
        .encode(
            x=alt.X("value:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(grid=True, gridColor=RING, format="~s")),
            y=alt.Y("paper_id:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=200)),
            color=alt.Color("status:N",
                            scale=alt.Scale(domain=[t["reported"], t["needs"]], range=[ACCENT, AMBER]),
                            legend=alt.Legend(title=None, orient="top", labelColor=INK2)),
            tooltip=[alt.Tooltip("paper_id:N"), alt.Tooltip("value:Q", title=quantity),
                     alt.Tooltip("species:N"), alt.Tooltip("src:N", title="source")],
        )
        .properties(height=max(240, 22 * len(d)))
        .configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(labelColor=INK2, titleColor=INK2)
    )
    return chart


with tab_ov:
    st.info(t["note_purity"])
    st.markdown(f"#### {t['purity_h']}")
    st.markdown(f'<p class="llead">{t["purity_n"]}</p>', unsafe_allow_html=True)
    st.altair_chart(bar_chart(seed_num, "protein_purity_pct", t["purity_h"]), width="stretch")
    st.markdown(f"#### {t['yield_h']}")
    st.markdown(f'<p class="llead">{t["yield_n"]}</p>', unsafe_allow_html=True)
    st.altair_chart(bar_chart(seed_num, "yield_pct", t["yield_h"]), width="stretch")


with tab_ex:
    st.markdown(f"### {t['ex_h']}")
    st.warning(t["ex_warn"])
    st.markdown(f'<p class="llead">{t["ex_n"]}</p>', unsafe_allow_html=True)
    exd = llm_num.copy()
    fx = st.columns([1.6, 1.4, 1])
    exq = fx[0].text_input(t["ex_search"], "", key="ex_q")
    exp = fx[1].multiselect(t["ex_paper"], sorted(exd.paper_id.unique()), key="ex_paper")
    exflag = fx[2].checkbox(t["ex_only_flag"], key="ex_flag")
    if exp:
        exd = exd[exd.paper_id.isin(exp)]
    if exflag:
        exd = exd[exd.needs_human == 1]
    if exq:
        hay = (exd.quantity.fillna("") + " " + exd.paper_id + " "
               + exd.source_location.fillna("")).str.lower()
        exd = exd[hay.str.contains(re.escape(exq.lower()))]
    st.caption(f"{t['showing']} {len(exd)} {t['of']} {len(llm_num)}")
    show = exd[["paper_id", "quantity", "value", "unit", "treatment_condition",
                "needs_human", "source_location"]].rename(
        columns={"paper_id": "paper", "needs_human": "⚠", "source_location": "source (verbatim)"})
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={"value": st.column_config.NumberColumn(format="%.3g")})


with tab_corpus:
    st.markdown(f"### {t['filters']}")
    fc = st.columns([2, 1.4, 1.4])
    q = fc[0].text_input(t["f_search"], "")
    fsp = fc[1].multiselect(t["f_species"], sorted(papers.species.unique()))
    frel = fc[2].multiselect(t["f_rel"], ["High", "Medium", "Low"])
    fflag = st.checkbox(t["f_flag"], value=False)

    view = papers.copy()
    if fsp:
        view = view[view.species.isin(fsp)]
    if frel:
        view = view[view.relevance.isin(frel)]
    if fflag:
        view = view[view["n_flags"] > 0]
    if q:
        ql = q.lower()
        hay = (view.paper_id + " " + view.title.fillna("") + " " + view.system.fillna("")
               + " " + view.extraction_method_family.fillna("")).str.lower()
        view = view[hay.str.contains(re.escape(ql))]

    st.caption(f"{t['showing']} {len(view)} {t['of']} {len(papers)} {t['papers']}")
    show = view[["paper_id", "year", "species", "relevance", "verification_level",
                 "purity", "yield", "n_flags"]].rename(columns={
        "paper_id": "paper", "verification_level": "text level", "n_flags": "⚠ flags"})
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={
                     "purity": st.column_config.NumberColumn(
                         "protein %", format="%.1f", help="Protein CONTENT of the isolate (how pure)."),
                     "yield": st.column_config.NumberColumn(
                         "yield %", format="%.1f",
                         help="How MUCH protein was recovered, as % of the protein in the leaf. "
                              "High purity + low yield = a pure product but little of it."),
                     "⚠ flags": st.column_config.NumberColumn(
                         "⚠", help="How many of this paper's numbers are flagged needs-verify.")})

    if len(view) == 0:
        st.info(t["no_rows"])
    for _, p in view.iterrows():
        flag = " ⚠" if p["n_flags"] else ""
        with st.expander(f"{p.paper_id} · {p.year_str} · {p.species}{flag}"):
            st.markdown(f"**{p.title or ''}**")
            if p.scientific_story:
                st.markdown(f"*{p.scientific_story}*")
            st.markdown("  ".join(f'<span class="chip">{c}</span>' for c in p.cats),
                        unsafe_allow_html=True)
            if p.key_findings:
                st.markdown(f"**{t['findings']}**")
                st.markdown(f'<div style="max-height:280px;overflow:auto;color:{INK2};font-size:.86rem;'
                            f'white-space:pre-wrap">{p.key_findings}</div>', unsafe_allow_html=True)
            meta = " · ".join(x for x in [f"doi: {clean_text(p.doi)}" if clean_text(p.doi) else "", clean_text(p.source_type)] if x)
            if meta:
                st.caption(meta)


with tab_ai:
    st.markdown(f'<p class="llead">{t["ai_intro"]}</p>', unsafe_allow_html=True)

    def ai_card(p):
        techs = "  ".join(f'<span class="chip tech">{TECH_LABEL.get(x, x)}</span>' for x in p.analysis)
        st.markdown(f"""<div class="aicard">
           <div style="font-family:ui-monospace,Menlo,monospace;color:{INK}">{p.paper_id}
             <span style="color:{INK2}">· {p.year_str}</span></div>
           <div style="margin:6px 0">{techs}
             <span class="chip sys">{(p.system or '')[:70]}</span></div>
           <div class="transfer">{p.scientific_story or ''}</div>
           </div>""", unsafe_allow_html=True)

    core = papers[papers.analysis.map(lambda a: any(x in a for x in ("ML", "deep_learning", "digital_twin")))]
    other = papers[papers.analysis.map(lambda a: bool(a)) &
                   ~papers.paper_id.isin(core.paper_id)]

    st.markdown(f"### {t['ai_core']}")
    st.markdown(f'<p class="llead">{t["ai_core_n"]}</p>', unsafe_allow_html=True)
    for _, p in core.sort_values("paper_id").iterrows():
        ai_card(p)

    if len(other):
        st.markdown(f"### {t['ai_other']}")
        st.markdown(f'<p class="llead">{t["ai_other_n"]}</p>', unsafe_allow_html=True)
        for _, p in other.sort_values("paper_id").iterrows():
            ai_card(p)


with tab_cats:
    st.markdown(f"### {t['cats_h']}")
    st.markdown(f'<p class="llead">{t["cats_n"]}</p>', unsafe_allow_html=True)
    cc = cats.copy()
    cc["group"] = cc.category.str.split(":").str[0]
    counts = cc.category.value_counts().reset_index()
    counts.columns = ["category", "n"]
    counts["group"] = counts.category.str.split(":").str[0]
    chart = (
        alt.Chart(counts).mark_bar(cornerRadiusEnd=4, height=16)
        .encode(
            x=alt.X("n:Q", title=None, axis=alt.Axis(grid=True, gridColor=RING)),
            y=alt.Y("category:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=220)),
            color=alt.Color("group:N", legend=alt.Legend(title=None, orient="top", labelColor=INK2),
                            scale=alt.Scale(scheme="tableau10")),
            tooltip=["category", "n"],
        )
        .properties(height=max(300, 20 * len(counts)))
        .configure_view(strokeWidth=0, fill=SURFACE)
    )
    st.altair_chart(chart, width="stretch")

with tab_norm:
    st.markdown(f"### {t['norm_h']}")
    st.markdown(f'<p class="llead">{t["norm_n"]}</p>', unsafe_allow_html=True)
    # study-count per quantity, shown at selection time (so a 1-study parameter is obvious)
    qcounts = numeric.groupby("quantity").paper_id.nunique().to_dict()
    only_sensory = st.checkbox(t["norm_sensory_only"], key="norm_sens")
    quants = [q for q in sorted(qcounts, key=lambda x: (-qcounts[x], x))
              if (not only_sensory or q_is_sensory(q))]
    if not quants:
        st.info(t["norm_none"])
    else:
        default_ix = quants.index("protein_purity_pct") if "protein_purity_pct" in quants else 0
        qsel = st.selectbox(
            t["norm_pick"], quants, index=default_ix,
            format_func=lambda q: f"{'👃 ' if q_is_sensory(q) else ''}{q_friendly(q)}  ·  {qcounts[q]} "
                                  f"{'study' if qcounts[q] == 1 else 'studies'}")
        d = numeric[numeric.quantity == qsel].copy()
        units = ", ".join(sorted({str(u) for u in d.unit.dropna().unique()})) or "—"
        st.caption(f"{t['norm_learnable']}: {d.paper_id.nunique()}   ·   {t['norm_unit']}: {units}"
                   + (f"   ·   👃 {t['norm_is_sensory']}" if q_is_sensory(qsel) else ""))
        if d.paper_id.nunique() < 2:
            st.warning(t["norm_thin"])
        d["prov"] = d.provenance.map(lambda p: "seed" if p == "seed" else "extracted")
        dot = (
            alt.Chart(d).mark_circle(size=95, opacity=.8).encode(
                x=alt.X("value:Q", title=q_friendly(qsel)),
                y=alt.Y("paper_id:N", sort="-x", title=None,
                        axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace", labelLimit=200)),
                color=alt.Color("prov:N", scale=alt.Scale(domain=["seed", "extracted"], range=[ACCENT, CYAN]),
                                legend=alt.Legend(title=None, orient="top", labelColor=INK2)),
                tooltip=["paper_id", "value", "unit", "species", "treatment_condition", "provenance", "source_location"],
            ).properties(height=max(240, 20 * d.paper_id.nunique()))
            .configure_view(strokeWidth=0, fill=SURFACE).configure_axis(labelColor=INK2, titleColor=INK2))
        st.altair_chart(dot, width="stretch")
        st.dataframe(
            d[["paper_id", "value", "unit", "species", "treatment_condition", "sd_error",
               "n_replicates", "provenance", "source_location"]].sort_values("value", ascending=False),
            width="stretch", hide_index=True)


with tab_verify:
    st.markdown(f"### {t['ver_h']}")
    st.markdown(f'<p class="llead">{t["ver_n"]}</p>', unsafe_allow_html=True)
    st.info(t["ver_how"])
    if READ_ONLY:
        st.warning(t["ro_banner"])
    _pm_path = os.path.join(os.path.dirname(DB_PATH), "pdf_sources.json")
    pdf_base = {}
    if os.path.exists(_pm_path):
        for k, v in json.load(open(_pm_path, encoding="utf-8")).items():
            if not k.startswith("_"):
                pdf_base[k] = os.path.basename(v)
    scope = st.radio(t["ver_scope"], [t["ver_flagged"], t["ver_all"]], horizontal=True)
    vdf = numeric.copy()
    vdf["verified"] = vdf["verified"].fillna(0).astype(int) if "verified" in vdf.columns else 0
    if scope == t["ver_flagged"]:
        vdf = vdf[(vdf.needs_human == 1) & (vdf.verified == 0)]
    vdf["pdf"] = vdf.paper_id.map(pdf_base).fillna("— (no local PDF)")
    vcols = ["result_id", "paper_id", "pdf", "quantity", "value", "unit", "provenance",
             "needs_human", "verified", "verified_value", "verified_note", "source_location"]
    vdf = vdf[vcols].copy()
    vdf["verified"] = vdf["verified"].astype(bool)
    if len(vdf) == 0:
        st.success(t["ver_none"])
    elif READ_ONLY:
        st.dataframe(vdf.drop(columns=["result_id"]).rename(
            columns={"pdf": t["ver_pdf"], "source_location": "source (verbatim)"}),
            width="stretch", hide_index=True)
    else:
        st.caption(f"{len(vdf)} rows")
        edited = st.data_editor(
            vdf, width="stretch", hide_index=True, key="verify_editor",
            disabled=["result_id", "paper_id", "pdf", "quantity", "unit", "provenance",
                      "needs_human", "source_location"],
            column_config={
                "pdf": st.column_config.TextColumn(t["ver_pdf"]),
                "verified": st.column_config.CheckboxColumn("✓ verified"),
                "value": st.column_config.NumberColumn("value", format="%.4g"),
                "verified_value": st.column_config.NumberColumn("corrected value", format="%.4g"),
                "verified_note": st.column_config.TextColumn("note"),
                "source_location": st.column_config.TextColumn("source (verbatim)", width="large"),
            })
        if st.button(t["ver_save"], type="primary"):
            orig = vdf.set_index("result_id")
            ed = edited.set_index("result_id")
            con = sqlite3.connect(DB_PATH)
            n = 0
            for rid in ed.index:
                o, e = orig.loc[rid], ed.loc[rid]
                changed = (bool(o.verified) != bool(e.verified)
                           or (o.value != e.value) or (str(o.verified_note) != str(e.verified_note))
                           or (str(o.verified_value) != str(e.verified_value)))
                if not changed:
                    continue
                con.execute(
                    """UPDATE numeric_results
                       SET value=?, verified=?, verified_value=?, verified_note=?,
                           verified_date=?, needs_human=CASE WHEN ?=1 THEN 0 ELSE needs_human END
                       WHERE result_id=?""",
                    (float(e.value) if pd.notna(e.value) else None, int(bool(e.verified)),
                     float(e.verified_value) if pd.notna(e.verified_value) else None,
                     (e.verified_note or None), date.today().isoformat(),
                     int(bool(e.verified)), int(rid)))
                n += 1
            con.commit()
            con.close()
            st.success(f"{t['ver_saved']} ({n})")
            st.cache_data.clear()
            st.rerun()


with tab_gaps:
    st.markdown(f"### {t['gaps_h']}")
    st.markdown(f'<p class="llead">{t["gaps_n"]}</p>', unsafe_allow_html=True)
    outc = cats[cats.category.str.startswith("outcome:")].copy()
    outc["outcome"] = outc.category.str.split(":").str[1]
    m = outc.merge(papers[["paper_id", "species"]], on="paper_id")
    if len(m):
        mm = m.groupby(["species", "outcome"]).size().reset_index(name="n")
        heat = (
            alt.Chart(mm).mark_rect().encode(
                x=alt.X("outcome:N", title=None, axis=alt.Axis(labelColor=INK2, labelAngle=-30)),
                y=alt.Y("species:N", title=None, axis=alt.Axis(labelColor=INK2, labelFont="ui-monospace")),
                color=alt.Color("n:Q", scale=alt.Scale(scheme="greens"),
                                legend=alt.Legend(title="papers", labelColor=INK2)),
                tooltip=["species", "outcome", "n"],
            ).properties(height=max(260, 22 * m.species.nunique()))
            .configure_view(strokeWidth=0, fill=SURFACE))
        st.altair_chart(heat, width="stretch")
    st.markdown(f"#### {t['gaps_sensory']}")
    sc = st.columns(4)
    for i, oc in enumerate(["off_flavor", "off_odor", "color", "protein_purity"]):
        n = outc[outc.outcome == oc].paper_id.nunique()
        sc[i].metric(oc, n)


with tab_compare:
    st.markdown(f"### {t['cmp_h']}")
    sel = st.multiselect(t["cmp_pick"], sorted(papers.paper_id), max_selections=4)
    if sel:
        sub = papers[papers.paper_id.isin(sel)].set_index("paper_id")
        st.dataframe(sub[["year_str", "species", "relevance", "verification_level",
                          "extraction_method_family", "purity", "yield"]].T, width="stretch")
        nn = seed_num[seed_num.paper_id.isin(sel)]
        if len(nn):
            piv = nn.pivot_table(index="quantity", columns="paper_id", values="value", aggfunc="first")
            st.dataframe(piv, width="stretch")
    st.divider()
    st.markdown(f"### {t['qry_h']}")
    st.markdown(f'<p class="llead">{t["qry_n"]}</p>', unsafe_allow_html=True)
    qc = st.columns(3)
    qq = qc[0].multiselect(t["norm_pick"], sorted(numeric.quantity.dropna().unique()))
    qs = qc[1].multiselect(t["f_species"], sorted(numeric.species.dropna().unique()))
    qp = qc[2].radio(t["qry_prov"], ["seed+extracted", "seed", "extracted"], horizontal=True)
    qd = numeric.copy()
    if qq:
        qd = qd[qd.quantity.isin(qq)]
    if qs:
        qd = qd[qd.species.isin(qs)]
    if qp == "seed":
        qd = qd[qd.provenance == "seed"]
    elif qp == "extracted":
        qd = qd[qd.provenance.str.startswith("llm:")]
    out = qd[["paper_id", "quantity", "value", "unit", "species", "treatment_condition",
              "provenance", "needs_human", "source_location"]]
    st.caption(f"{len(out)} rows")
    st.dataframe(out, width="stretch", hide_index=True)
    st.download_button(t["qry_dl"], out.to_csv(index=False).encode("utf-8"),
                       "leaf_query.csv", "text/csv")


st.markdown(f'<div class="foot">{t["prov"]} · db/leaf_lit.db · schema v1</div>',
            unsafe_allow_html=True)
