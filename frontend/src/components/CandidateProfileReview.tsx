import React, { useState } from "react";
import { ExtractionResultData } from "./ExtractionReview";

export type ExtractedField = {
  fieldName: string;
  value: string | null;
  normalizedValue: string | null;
  confidence: number | null;
  confidenceBand: string;
  evidenceIds: string[];
  extractionMethod: string | null;
  reviewStatus: string;
};

export type ExperienceRecord = {
  jobTitle: ExtractedField;
  organization: ExtractedField;
  startDate: ExtractedField;
  endDate: ExtractedField;
  descriptions: ExtractedField[];
};

export type EducationRecord = {
  degree: ExtractedField;
  fieldOfStudy?: ExtractedField | null;
  institution: ExtractedField;
  startDate: ExtractedField;
  endDate: ExtractedField;
  grade: ExtractedField;
};

export type ProjectRecord = {
  name: ExtractedField;
  description: ExtractedField;
  technologies: ExtractedField[];
  projectUrl: ExtractedField;
};

export type CertificationRecord = {
  name: ExtractedField;
  issuer: ExtractedField;
  issuedDate: ExtractedField;
  expiryDate?: ExtractedField | null;
  credentialId?: ExtractedField | null;
  credentialUrl: ExtractedField;
};

export type CandidateIdentity = {
  resumeArtifactId: string;
  fullName: ExtractedField;
  emails: ExtractedField[];
  phoneNumbers: ExtractedField[];
  linkedin: ExtractedField;
  github: ExtractedField;
  portfolio: ExtractedField;
  location: ExtractedField;
};

export type CandidateProfessionalProfile = {
  headline: ExtractedField;
  summary: ExtractedField;
  skills: ExtractedField[];
  employment: ExperienceRecord[];
  education: EducationRecord[];
  projects: ProjectRecord[];
  certifications: CertificationRecord[];
  languages: ExtractedField[];
  awards: ExtractedField[];
  publications: ExtractedField[];
};

export type EvidenceSpan = {
  evidenceId: string;
  resumeArtifactId: string;
  pageNumber: number | null;
  blockNumber: number | null;
  characterStart: number;
  characterEnd: number;
  originalText: string;
  extractionMethod: string;
};

export type ProfileWarning = {
  code: string;
  category: string;
  message?: string | null;
  fieldName?: string | null;
  count?: number | null;
  evidenceId?: string | null;
};

export type CandidateProfileData = {
  artifactId: string;
  profileId: string;
  profileVersion: number;
  schemaVersion: string;
  parserPipelineVersion: string;
  reviewRequired: boolean;
  warnings: ProfileWarning[];
  identity: CandidateIdentity;
  professionalProfile: CandidateProfessionalProfile;
  evidence: EvidenceSpan[];
};

interface CandidateProfileReviewProps {
  profile: CandidateProfileData;
  extraction?: ExtractionResultData | null;
  onReset: () => void;
}

export function CandidateProfileReview({ profile, onReset }: CandidateProfileReviewProps) {
  const { identity, professionalProfile, evidence } = profile;
  const [expandedEvidenceKey, setExpandedEvidenceKey] = useState<string | null>(null);

  const evidenceMap = new Map<string, EvidenceSpan>();
  evidence.forEach((ev) => evidenceMap.set(ev.evidenceId, ev));

  const toggleEvidence = (key: string) => {
    setExpandedEvidenceKey((prev) => (prev === key ? null : key));
  };

  const renderEvidenceAccordion = (key: string, evidenceIds: string[]) => {
    if (!evidenceIds || evidenceIds.length === 0) return null;
    const isExpanded = expandedEvidenceKey === key;
    const matchingSpans = evidenceIds
      .map((id) => evidenceMap.get(id))
      .filter((s): s is EvidenceSpan => Boolean(s));

    if (matchingSpans.length === 0) return null;

    return (
      <div className="evidence-accordion-wrapper">
        <button
          type="button"
          className="btn-evidence-toggle"
          onClick={() => toggleEvidence(key)}
          aria-expanded={isExpanded}
        >
          🔍 {isExpanded ? "Hide Evidence" : `View Evidence (${matchingSpans.length})`}
        </button>
        {isExpanded && (
          <div className="evidence-panel">
            {matchingSpans.map((span) => (
              <div key={span.evidenceId} className="evidence-item-card">
                <div className="evidence-meta-row">
                  <span className="badge badge-index">
                    Block #{span.blockNumber !== null ? span.blockNumber : "N/A"}
                  </span>
                  {span.pageNumber !== null && (
                    <span className="badge badge-type">Page {span.pageNumber}</span>
                  )}
                  <span className="evidence-method">{span.extractionMethod}</span>
                  <span className="evidence-offsets mono">
                    chars [{span.characterStart}:{span.characterEnd}]
                  </span>
                </div>
                <div className="evidence-snippet">
                  &ldquo;{span.originalText}&rdquo;
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderDateInterval = (startDate: ExtractedField, endDate: ExtractedField) => {
    if (startDate.value && endDate.value) {
      return `${startDate.value} — ${endDate.value}`;
    }
    if (startDate.value) {
      return `${startDate.value} — Present`;
    }
    if (endDate.value) {
      return `Until ${endDate.value}`;
    }
    return "Date Not Specified";
  };

  return (
    <section className="profile-review-container" aria-labelledby="profile-review-title">
      {/* Header Bar */}
      <div className="extraction-review-header">
        <div>
          <h2 id="profile-review-title" className="extraction-review-title">
            Candidate Profile Review
          </h2>
          <p className="extraction-meta-subtitle">
            Pipeline: <span className="mono">{profile.parserPipelineVersion}</span> &bull; Version:{" "}
            <span className="mono">{profile.profileVersion}</span>
          </p>
        </div>
        <button type="button" onClick={onReset} className="btn btn-secondary btn-sm">
          Upload Another Document
        </button>
      </div>

      {/* Review Required Banner */}
      {profile.reviewRequired && (
        <div className="review-required-banner" role="alert">
          <span className="warning-icon" aria-hidden="true">⚠️</span>
          <div>
            <strong>Manual Review Required</strong>
            <p>
              Parser ambiguity or potential extraction anomalies were detected.
              Please inspect the highlighted fields and evidence references.
            </p>
          </div>
        </div>
      )}

      {/* Warning Breakdown */}
      {profile.warnings.length > 0 && (
        <div className="warning-breakdown-card">
          <h3 className="section-subtitle">Extraction Quality &amp; Parser Warnings ({profile.warnings.length})</h3>
          <ul className="warning-list">
            {profile.warnings.map((w, idx) => (
              <li key={idx} className="warning-item">
                <span className="badge badge-review-warn">{w.code}</span>
                <span className="warning-cat">[{w.category}]</span>
                {w.fieldName && <span> Field: <strong>{w.fieldName}</strong></span>}
                {w.message && <span> - {w.message}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 1. Identity & Contact Information (Visibly Separated) */}
      <div className="profile-section-card identity-card">
        <div className="section-card-header">
          <span className="section-icon">👤</span>
          <div>
            <h3 className="section-title">Candidate Identity &amp; Contact Details</h3>
            <p className="section-caption">Isolated from matcher-facing features</p>
          </div>
        </div>

        <div className="identity-grid">
          <div className="field-group">
            <label className="field-label">Full Name</label>
            <div className="field-value">{identity.fullName.value || <span className="null-val">Not Detected</span>}</div>
            {identity.fullName.confidence && (
              <span className="badge badge-confidence">{(identity.fullName.confidence * 100).toFixed(0)}% conf</span>
            )}
            {renderEvidenceAccordion("identity-fullname", identity.fullName.evidenceIds)}
          </div>

          <div className="field-group">
            <label className="field-label">Email(s)</label>
            <div className="field-value">
              {identity.emails.length > 0 ? (
                identity.emails.map((e, i) => <div key={i}>{e.value}</div>)
              ) : (
                <span className="null-val">Not Detected</span>
              )}
            </div>
            {renderEvidenceAccordion(
              "identity-emails",
              identity.emails.flatMap((e) => e.evidenceIds)
            )}
          </div>

          <div className="field-group">
            <label className="field-label">Phone Number(s)</label>
            <div className="field-value">
              {identity.phoneNumbers.length > 0 ? (
                identity.phoneNumbers.map((p, i) => <div key={i}>{p.value}</div>)
              ) : (
                <span className="null-val">Not Detected</span>
              )}
            </div>
            {renderEvidenceAccordion(
              "identity-phones",
              identity.phoneNumbers.flatMap((p) => p.evidenceIds)
            )}
          </div>

          <div className="field-group">
            <label className="field-label">Location</label>
            <div className="field-value">{identity.location.value || <span className="null-val">Not Detected</span>}</div>
          </div>

          <div className="field-group">
            <label className="field-label">Professional Links</label>
            <div className="field-value">
              {identity.linkedin.value && <div>LinkedIn: {identity.linkedin.value}</div>}
              {identity.github.value && <div>GitHub: {identity.github.value}</div>}
              {identity.portfolio.value && <div>Portfolio: {identity.portfolio.value}</div>}
              {!identity.linkedin.value && !identity.github.value && !identity.portfolio.value && (
                <span className="null-val">None Provided</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Professional Profile Features */}
      {/* Headline & Summary */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">💼</span>
          <h3 className="section-title">Professional Summary &amp; Headline</h3>
        </div>

        {professionalProfile.headline.value && (
          <div className="field-group mb-3">
            <label className="field-label">Headline</label>
            <div className="headline-text">{professionalProfile.headline.value}</div>
          </div>
        )}

        <div className="field-group">
          <label className="field-label">Summary</label>
          <div className="summary-text">
            {professionalProfile.summary.value || <span className="null-val">No summary statement provided</span>}
          </div>
          {renderEvidenceAccordion("summary-evidence", professionalProfile.summary.evidenceIds)}
        </div>
      </div>

      {/* Skills */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">⚡</span>
          <h3 className="section-title">Extracted Skills ({professionalProfile.skills.length})</h3>
        </div>
        <div className="skills-tag-cloud">
          {professionalProfile.skills.length > 0 ? (
            professionalProfile.skills.map((sk, i) => (
              <span key={i} className="skill-pill">
                {sk.value}
                {sk.confidence && (
                  <span className="skill-conf">{(sk.confidence * 100).toFixed(0)}%</span>
                )}
              </span>
            ))
          ) : (
            <span className="null-val">No skills extracted</span>
          )}
        </div>
      </div>

      {/* Employment History */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🏢</span>
          <h3 className="section-title">Employment History ({professionalProfile.employment.length})</h3>
        </div>
        {professionalProfile.employment.length > 0 ? (
          <div className="timeline-list">
            {professionalProfile.employment.map((emp, i) => {
              const allEmpEvIds = [
                ...emp.jobTitle.evidenceIds,
                ...emp.organization.evidenceIds,
                ...emp.startDate.evidenceIds,
                ...emp.endDate.evidenceIds,
                ...emp.descriptions.flatMap((d) => d.evidenceIds),
              ];
              return (
                <div key={i} className="timeline-item">
                  <div className="timeline-header">
                    <div>
                      <h4 className="timeline-role">{emp.jobTitle.value || "Role Not Specified"}</h4>
                      <span className="timeline-org">{emp.organization.value || "Organization Not Specified"}</span>
                    </div>
                    <span className="timeline-date">
                      {renderDateInterval(emp.startDate, emp.endDate)}
                    </span>
                  </div>
                  {emp.descriptions.length > 0 && (
                    <ul className="timeline-bullets">
                      {emp.descriptions.map((desc, dIdx) => (
                        <li key={dIdx}>{desc.value}</li>
                      ))}
                    </ul>
                  )}
                  {renderEvidenceAccordion(`emp-${i}`, allEmpEvIds)}
                </div>
              );
            })}
          </div>
        ) : (
          <span className="null-val">No employment records extracted</span>
        )}
      </div>

      {/* Education */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🎓</span>
          <h3 className="section-title">Education ({professionalProfile.education.length})</h3>
        </div>
        {professionalProfile.education.length > 0 ? (
          <div className="timeline-list">
            {professionalProfile.education.map((edu, i) => {
              const allEduEvIds = [
                ...edu.degree.evidenceIds,
                ...(edu.fieldOfStudy ? edu.fieldOfStudy.evidenceIds : []),
                ...edu.institution.evidenceIds,
                ...edu.startDate.evidenceIds,
                ...edu.endDate.evidenceIds,
                ...edu.grade.evidenceIds,
              ];
              return (
                <div key={i} className="timeline-item">
                  <div className="timeline-header">
                    <div>
                      <h4 className="timeline-role">
                        {edu.degree.value || "Degree Not Specified"}
                        {edu.fieldOfStudy && edu.fieldOfStudy.value && (
                          <span className="field-of-study"> in {edu.fieldOfStudy.value}</span>
                        )}
                      </h4>
                      <span className="timeline-org">{edu.institution.value || "Institution Not Specified"}</span>
                    </div>
                    <span className="timeline-date">
                      {renderDateInterval(edu.startDate, edu.endDate)}
                    </span>
                  </div>
                  {edu.grade.value && (
                    <div className="grade-badge">Grade/GPA: {edu.grade.value}</div>
                  )}
                  {renderEvidenceAccordion(`edu-${i}`, allEduEvIds)}
                </div>
              );
            })}
          </div>
        ) : (
          <span className="null-val">No education records extracted</span>
        )}
      </div>

      {/* Projects */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🚀</span>
          <h3 className="section-title">Projects ({professionalProfile.projects.length})</h3>
        </div>
        {professionalProfile.projects.length > 0 ? (
          <div className="projects-grid">
            {professionalProfile.projects.map((proj, i) => {
              const allProjEvIds = [
                ...proj.name.evidenceIds,
                ...proj.description.evidenceIds,
                ...proj.technologies.flatMap((t) => t.evidenceIds),
                ...proj.projectUrl.evidenceIds,
              ];
              return (
                <div key={i} className="project-card">
                  <h4 className="project-name">{proj.name.value || "Project"}</h4>
                  {proj.description.value && <p className="project-desc">{proj.description.value}</p>}
                  {proj.technologies.length > 0 && (
                    <div className="project-tech-tags">
                      {proj.technologies.map((t, ti) => (
                        <span key={ti} className="badge badge-type">{t.value}</span>
                      ))}
                    </div>
                  )}
                  {proj.projectUrl.value && (
                    <div className="project-link mono">{proj.projectUrl.value}</div>
                  )}
                  {renderEvidenceAccordion(`proj-${i}`, allProjEvIds)}
                </div>
              );
            })}
          </div>
        ) : (
          <span className="null-val">No projects extracted</span>
        )}
      </div>

      {/* Certifications & Languages */}
      <div className="profile-two-col-grid">
        {/* Certifications */}
        <div className="profile-section-card">
          <div className="section-card-header">
            <span className="section-icon">📜</span>
            <h3 className="section-title">Certifications ({professionalProfile.certifications.length})</h3>
          </div>
          {professionalProfile.certifications.length > 0 ? (
            <ul className="cert-list">
              {professionalProfile.certifications.map((cert, i) => {
                const allCertEvIds = [
                  ...cert.name.evidenceIds,
                  ...cert.issuer.evidenceIds,
                  ...cert.issuedDate.evidenceIds,
                  ...(cert.expiryDate ? cert.expiryDate.evidenceIds : []),
                  ...(cert.credentialId ? cert.credentialId.evidenceIds : []),
                  ...cert.credentialUrl.evidenceIds,
                ];
                return (
                  <li key={i} className="cert-item">
                    <strong className="cert-title">{cert.name.value}</strong>
                    {cert.issuer.value && <div className="cert-meta-field"><span className="meta-label">Issuer:</span> {cert.issuer.value}</div>}
                    {cert.issuedDate.value && <div className="cert-meta-field"><span className="meta-label">Issued:</span> {cert.issuedDate.value}</div>}
                    {cert.expiryDate && cert.expiryDate.value && <div className="cert-meta-field"><span className="meta-label">Expires:</span> {cert.expiryDate.value}</div>}
                    {cert.credentialId && cert.credentialId.value && <div className="cert-meta-field"><span className="meta-label">Credential ID:</span> <span className="mono">{cert.credentialId.value}</span></div>}
                    {cert.credentialUrl.value && <div className="cert-meta-field"><span className="meta-label">Credential URL:</span> <span className="mono">{cert.credentialUrl.value}</span></div>}
                    {renderEvidenceAccordion(`cert-${i}`, allCertEvIds)}
                  </li>
                );
              })}
            </ul>
          ) : (
            <span className="null-val">No certifications extracted</span>
          )}
        </div>

        {/* Languages */}
        <div className="profile-section-card">
          <div className="section-card-header">
            <span className="section-icon">🌐</span>
            <h3 className="section-title">Languages ({professionalProfile.languages.length})</h3>
          </div>
          {professionalProfile.languages.length > 0 ? (
            <ul className="lang-list">
              {professionalProfile.languages.map((l, i) => {
                const hasProficiency = l.normalizedValue && l.normalizedValue.toLowerCase() !== l.value?.toLowerCase();
                return (
                  <li key={i} className="lang-item">
                    <span className="lang-name">{l.value}</span>
                    {hasProficiency && (
                      <span className="badge badge-index">{l.normalizedValue}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <span className="null-val">No languages extracted</span>
          )}
        </div>
      </div>
    </section>
  );
}
