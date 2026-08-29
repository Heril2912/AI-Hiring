import React from "react";
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
  const { identity, professionalProfile } = profile;

  return (
    <section className="profile-review-container" aria-labelledby="profile-review-title">
      {/* Header Bar */}
      <div className="extraction-review-header">
        <div>
          <h2 id="profile-review-title" className="extraction-review-title">
            Candidate Profile Review
          </h2>
          <p className="extraction-meta-subtitle">
            Schema Version: <span className="mono">{profile.schemaVersion}</span> &bull; Profile ID:{" "}
            <span className="mono">{profile.profileId.slice(0, 8)}...</span>
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
            <p className="section-caption">Isolated from future matcher-facing features</p>
          </div>
        </div>

        <div className="identity-grid">
          <div className="field-group">
            <label className="field-label">Full Name</label>
            <div className="field-value">{identity.fullName.value || <span className="null-val">Not Detected</span>}</div>
            {identity.fullName.confidence && (
              <span className="badge badge-confidence">{(identity.fullName.confidence * 100).toFixed(0)}% conf</span>
            )}
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
            {professionalProfile.employment.map((emp, i) => (
              <div key={i} className="timeline-item">
                <div className="timeline-header">
                  <div>
                    <h4 className="timeline-role">{emp.jobTitle.value || "Role Not Specified"}</h4>
                    <span className="timeline-org">{emp.organization.value || "Organization Not Specified"}</span>
                  </div>
                  <span className="timeline-date">
                    {emp.startDate.value || "Start"} — {emp.endDate.value || "Present"}
                  </span>
                </div>
                {emp.descriptions.length > 0 && (
                  <ul className="timeline-bullets">
                    {emp.descriptions.map((desc, dIdx) => (
                      <li key={dIdx}>{desc.value}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
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
            {professionalProfile.education.map((edu, i) => (
              <div key={i} className="timeline-item">
                <div className="timeline-header">
                  <div>
                    <h4 className="timeline-role">{edu.degree.value || "Degree Not Specified"}</h4>
                    <span className="timeline-org">{edu.institution.value || "Institution Not Specified"}</span>
                  </div>
                  <span className="timeline-date">
                    {edu.startDate.value ? `${edu.startDate.value} — ` : ""}
                    {edu.endDate.value || ""}
                  </span>
                </div>
                {edu.grade.value && (
                  <div className="grade-badge">Grade/GPA: {edu.grade.value}</div>
                )}
              </div>
            ))}
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
            {professionalProfile.projects.map((proj, i) => (
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
              </div>
            ))}
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
              {professionalProfile.certifications.map((cert, i) => (
                <li key={i} className="cert-item">
                  <strong>{cert.name.value}</strong>
                  {cert.issuer.value && <div>Issuer: {cert.issuer.value}</div>}
                  {cert.issuedDate.value && <div>Issued: {cert.issuedDate.value}</div>}
                </li>
              ))}
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
              {professionalProfile.languages.map((l, i) => (
                <li key={i} className="lang-item">
                  <span className="lang-name">{l.value}</span>
                  {l.normalizedValue && l.normalizedValue !== l.value && (
                    <span className="badge badge-index">{l.normalizedValue}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <span className="null-val">No languages extracted</span>
          )}
        </div>
      </div>
    </section>
  );
}
