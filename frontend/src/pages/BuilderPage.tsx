import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createAgent,
  fetchPublicConfig,
  getOwnerSecret,
  setOwnerSecret,
  type AgentMeta,
} from "../api";

type Section = "profile" | "sources" | "faq";

const ALL_OPEN: Record<Section, boolean> = {
  profile: true,
  sources: true,
  faq: true,
};

export default function BuilderPage() {
  const [ownerRequired, setOwnerRequired] = useState(false);
  const [publicOnly, setPublicOnly] = useState(false);
  const [secretInput, setSecretInput] = useState(getOwnerSecret());
  const [unlocked, setUnlocked] = useState(Boolean(getOwnerSecret()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<AgentMeta | null>(null);
  const [copied, setCopied] = useState(false);
  // Independent open state — sections do not close each other
  const [openSections, setOpenSections] = useState<Record<Section, boolean>>(ALL_OPEN);

  useEffect(() => {
    fetchPublicConfig()
      .then((cfg) => {
        setOwnerRequired(cfg.owner_auth_required);
        setPublicOnly(cfg.public_chat_only);
        if (!cfg.owner_auth_required) setUnlocked(true);
        if (cfg.owner_auth_required && getOwnerSecret()) setUnlocked(true);
      })
      .catch((err) => setError(String(err.message || err)));
  }, []);

  function unlock(e: FormEvent) {
    e.preventDefault();
    setOwnerSecret(secretInput.trim());
    setUnlocked(true);
  }

  function toggle(section: Section) {
    setOpenSections((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setCreated(null);
    const form = new FormData(e.currentTarget);
    const faq = {
      open_to_relocate: String(form.get("open_to_relocate") || ""),
      work_authorization: String(form.get("work_authorization") || ""),
      preferred_roles: String(form.get("preferred_roles") || ""),
      preferred_locations: String(form.get("preferred_locations") || ""),
      notice_period: String(form.get("notice_period") || ""),
      compensation_notes: String(form.get("compensation_notes") || ""),
      other: String(form.get("other") || ""),
    };
    [
      "open_to_relocate",
      "work_authorization",
      "preferred_roles",
      "preferred_locations",
      "notice_period",
      "compensation_notes",
      "other",
    ].forEach((key) => form.delete(key));
    form.set("faq", JSON.stringify(faq));

    try {
      const agent = await createAgent(form);
      setCreated(agent);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!created) return;
    const url = `${window.location.origin}/a/${created.id}`;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (ownerRequired && !unlocked) {
    return (
      <main className="app-shell">
        <h1 className="brand">Profile RAG Agent</h1>
        <p className="lede">
          Owner access required. Enter the secret configured as OWNER_SECRET to build your agent.
        </p>
        <form className="panel gate" onSubmit={unlock}>
          <div className="field">
            <label htmlFor="owner">Owner secret</label>
            <input
              id="owner"
              type="password"
              value={secretInput}
              onChange={(e) => setSecretInput(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <button className="btn" type="submit">
            Unlock builder
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </main>
    );
  }

  return (
    <main className="app-shell">
      <h1 className="brand">Profile RAG Agent</h1>
      <p className="lede">
        Open-source RAG system for conversational profile discovery. Build from your resume, pasted
        profile text, and FAQs — then share one link with recruiters.
      </p>

      {publicOnly && (
        <p className="disclaimer" style={{ marginBottom: "1rem" }}>
          Public chat mode is on. Only owners with the secret can create agents here.
        </p>
      )}

      <form onSubmit={onSubmit}>
        <div className="panel">
          <section className="accordion-section">
            <button
              type="button"
              className="accordion-trigger"
              aria-expanded={openSections.profile}
              aria-controls="section-profile"
              onClick={() => toggle("profile")}
            >
              <span>
                Profile <span className="hint">name and headline</span>
              </span>
              <span className="chevron" aria-hidden>
                ▾
              </span>
            </button>
            {/* Keep mounted so uncontrolled inputs retain values when collapsed */}
            <div
              id="section-profile"
              className="accordion-panel"
              hidden={!openSections.profile}
            >
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="display_name">Display name</label>
                  <input id="display_name" name="display_name" required placeholder="Ada Lovelace" />
                </div>
                <div className="field">
                  <label htmlFor="headline">Headline</label>
                  <input
                    id="headline"
                    name="headline"
                    placeholder="ML engineer · RAG systems · open to relocate"
                  />
                </div>
              </div>
            </div>
          </section>

          <section className="accordion-section">
            <button
              type="button"
              className="accordion-trigger"
              aria-expanded={openSections.sources}
              aria-controls="section-sources"
              onClick={() => toggle("sources")}
            >
              <span>
                Sources <span className="hint">resume, LinkedIn, GitHub, notes</span>
              </span>
              <span className="chevron" aria-hidden>
                ▾
              </span>
            </button>
            <div
              id="section-sources"
              className="accordion-panel"
              hidden={!openSections.sources}
            >
              <div className="field">
                <label htmlFor="resume">Resume (PDF or Markdown)</label>
                <input id="resume" name="resume" type="file" accept=".pdf,.md,.txt" />
              </div>
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="linkedin_url">LinkedIn URL</label>
                  <input
                    id="linkedin_url"
                    name="linkedin_url"
                    placeholder="https://linkedin.com/in/..."
                  />
                </div>
                <div className="field">
                  <label htmlFor="github_username">GitHub username</label>
                  <input id="github_username" name="github_username" placeholder="octocat" />
                </div>
              </div>
              <div className="field">
                <label htmlFor="linkedin_text">LinkedIn About / Experience (paste)</label>
                <textarea
                  id="linkedin_text"
                  name="linkedin_text"
                  placeholder="Paste profile sections here. We do not scrape LinkedIn."
                />
              </div>
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="scholar_url">Google Scholar URL</label>
                  <input
                    id="scholar_url"
                    name="scholar_url"
                    placeholder="https://scholar.google.com/..."
                  />
                </div>
                <div className="field">
                  <label htmlFor="scholar_text">Publications (paste)</label>
                  <textarea
                    id="scholar_text"
                    name="scholar_text"
                    placeholder="Title — venue — year"
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="blog_text">Blog posts / project notes (paste Markdown)</label>
                <textarea id="blog_text" name="blog_text" />
              </div>
            </div>
          </section>

          <section className="accordion-section">
            <button
              type="button"
              className="accordion-trigger"
              aria-expanded={openSections.faq}
              aria-controls="section-faq"
              onClick={() => toggle("faq")}
            >
              <span>
                FAQ <span className="hint">relocation, roles, logistics</span>
              </span>
              <span className="chevron" aria-hidden>
                ▾
              </span>
            </button>
            <div id="section-faq" className="accordion-panel" hidden={!openSections.faq}>
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="open_to_relocate">Open to relocate?</label>
                  <input
                    id="open_to_relocate"
                    name="open_to_relocate"
                    placeholder="Yes — US and Canada"
                  />
                </div>
                <div className="field">
                  <label htmlFor="work_authorization">Work authorization</label>
                  <input id="work_authorization" name="work_authorization" />
                </div>
                <div className="field">
                  <label htmlFor="preferred_roles">Preferred roles</label>
                  <input id="preferred_roles" name="preferred_roles" />
                </div>
                <div className="field">
                  <label htmlFor="preferred_locations">Preferred locations</label>
                  <input id="preferred_locations" name="preferred_locations" />
                </div>
                <div className="field">
                  <label htmlFor="notice_period">Notice period</label>
                  <input id="notice_period" name="notice_period" />
                </div>
                <div className="field">
                  <label htmlFor="compensation_notes">Compensation notes (optional)</label>
                  <input id="compensation_notes" name="compensation_notes" />
                </div>
              </div>
              <div className="field">
                <label htmlFor="other">Other FAQ</label>
                <textarea id="other" name="other" />
              </div>
            </div>
          </section>
        </div>

        <div className="sticky-actions">
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Indexing…" : "Create agent"}
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      </form>

      {created && (
        <section className="success-card" aria-live="polite">
          <p className="ok">
            Agent ready for {created.display_name} · {created.chunk_count} chunks · id {created.id}
          </p>
          <div className="actions">
            <Link className="btn" to={`/a/${created.id}`}>
              Open chat
            </Link>
            <button className="btn secondary" type="button" onClick={copyLink}>
              {copied ? "Copied" : "Copy public link"}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
