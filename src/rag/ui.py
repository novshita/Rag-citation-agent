"""Small web UI: ask a question, see the answer, and see each cited quote highlighted in its source.

Run with:  streamlit run src/rag/ui.py     (needs:  pip install -e ".[ui]")
"""

import time

import streamlit as st

from rag.highlight import highlight_html
from rag.pipeline import PipelineResult

STATUS_LABEL = {
    "answered": ":green[Answered]",
    "partial": ":orange[Partial answer]",
    "abstained": ":red[Abstained]",
}


def show_result(result: PipelineResult, seconds: float) -> None:
    answer = result.answer
    st.markdown(f"**{STATUS_LABEL[answer.status]}** · confidence {answer.confidence:.2f} · {seconds:.1f}s")
    st.write(answer.answer)
    if answer.reason:
        st.caption(f"Reason: {answer.reason}")

    by_id = {c.chunk_id: c for c in result.chunks}
    for number, claim in enumerate(answer.claims, start=1):
        st.markdown(f"**[{number}]** {claim.text}")
        for citation in claim.citations:
            where = citation.doc_id if citation.page is None else f"{citation.doc_id}, page {citation.page}"
            with st.expander(f"Source: {where}"):
                chunk = by_id.get(citation.chunk_id)
                if chunk is None:
                    st.write(citation.quote)
                else:
                    st.markdown(highlight_html(chunk.text, citation.quote).replace("\n", "<br>"),
                                unsafe_allow_html=True)

    with st.expander(f"Retrieved passages ({len(result.chunks)})"):
        gate = result.gate
        verdict = "passed" if gate.passed else f"stopped: {gate.reason}"
        st.caption(f"Relevance gate {verdict}")
        for chunk in result.chunks:
            where = chunk.doc_id if chunk.page is None else f"{chunk.doc_id}, page {chunk.page}"
            st.markdown(f"`{chunk.score:.3f}` {where}")


def run_app(ask) -> None:
    """The page. `ask(question) -> PipelineResult` is passed in so tests can use a fake."""
    st.set_page_config(page_title="RAG Citation Agent", page_icon=":mag:")
    st.title("RAG Citation Agent")
    st.caption("Answers come only from the indexed documents, with every quote checked against its source.")

    question = st.text_input("Ask a question about the documents")
    if st.button("Ask", type="primary") and question.strip():
        started = time.perf_counter()
        with st.spinner("Searching and answering..."):
            result = ask(question.strip())
        show_result(result, time.perf_counter() - started)


@st.cache_resource(show_spinner="Loading models...")
def _load_pipeline():
    from rag.config import load_settings
    from rag.runtime import build_ask

    return build_ask(load_settings())


if __name__ == "__main__":   # `streamlit run` executes this file as __main__; tests import it instead
    run_app(_load_pipeline())
