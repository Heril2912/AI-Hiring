import React, { useState, useRef } from "react";
import {
  RequirementCategory,
  RequirementEvidenceType,
  RequirementItem,
  RequirementNecessity,
  RequirementPriority,
} from "../../api/jobs";
import { SkillSearchItem } from "../../api/taxonomy";
import { Icon } from "../Icon";
import { TaxonomySkillAutocomplete } from "./TaxonomySkillAutocomplete";

interface RequirementCardProps {
  requirement: RequirementItem;
  index: number;
  totalCount: number;
  forceExpandMoreOptions?: boolean;
  onChange: (updated: RequirementItem) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

const ALL_EVIDENCE_TYPES: { type: RequirementEvidenceType; label: string }[] = [
  { type: "EMPLOYMENT", label: "Work Experience" },
  { type: "PROJECT", label: "Projects / Code" },
  { type: "EDUCATION", label: "Education" },
  { type: "CERTIFICATION", label: "Certifications" },
  { type: "SKILL_LIST", label: "Skills List" },
  { type: "PUBLICATION", label: "Publications" },
  { type: "PATENT", label: "Patents" },
  { type: "OTHER", label: "Other Sections" },
];

export function RequirementCard({
  requirement,
  index,
  totalCount,
  forceExpandMoreOptions = false,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: RequirementCardProps) {
  const [showMoreOptions, setShowMoreOptions] = useState(forceExpandMoreOptions);
  const [isEditingLabel, setIsEditingLabel] = useState(!requirement.label.trim());
  const [equivalentInput, setEquivalentInput] = useState("");
  const rationaleTextareaRef = useRef<HTMLTextAreaElement>(null);

  const isSkillCategory = requirement.category === "SKILL";
  const isMustHave = requirement.necessity === "MUST_HAVE";
  const isCritical = requirement.priority === "CRITICAL";
  const needsRationale = (isMustHave || isCritical) && !requirement.rationale?.trim();

  const handleSelectTaxonomySkill = (skill: SkillSearchItem) => {
    onChange({
      ...requirement,
      label: skill.canonicalLabel,
      taxonomySkillConceptId: skill.conceptId,
      category: "SKILL",
      origin: "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED",
    });
    setIsEditingLabel(false);
  };

  const handleUseCustomText = (text: string) => {
    onChange({
      ...requirement,
      label: text,
      taxonomySkillConceptId: null,
      origin: "RECRUITER_ENTERED",
    });
    setIsEditingLabel(false);
  };

  const handleCategoryChange = (newCat: RequirementCategory) => {
    const isNewSkill = newCat === "SKILL";
    onChange({
      ...requirement,
      category: newCat,
      // If changed to non-skill, clear taxonomy skill link
      taxonomySkillConceptId: isNewSkill ? requirement.taxonomySkillConceptId : null,
      origin: isNewSkill && requirement.taxonomySkillConceptId ? "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED" : "RECRUITER_ENTERED",
    });
  };

  const handleToggleEvidenceType = (evType: RequirementEvidenceType) => {
    const current = requirement.acceptedEvidenceTypes || [];
    const updated = current.includes(evType)
      ? current.filter((t) => t !== evType)
      : [...current, evType];
    onChange({ ...requirement, acceptedEvidenceTypes: updated });
  };

  const handleAddEquivalent = () => {
    const trimmed = equivalentInput.trim();
    if (!trimmed) return;
    const current = requirement.acceptedEquivalents || [];
    if (!current.includes(trimmed) && trimmed.toLowerCase() !== requirement.label.toLowerCase()) {
      onChange({ ...requirement, acceptedEquivalents: [...current, trimmed] });
    }
    setEquivalentInput("");
  };

  const handleRemoveEquivalent = (eq: string) => {
    const current = requirement.acceptedEquivalents || [];
    onChange({ ...requirement, acceptedEquivalents: current.filter((e) => e !== eq) });
  };

  const handleFocusRationale = () => {
    setShowMoreOptions(true);
    setTimeout(() => {
      rationaleTextareaRef.current?.focus();
    }, 50);
  };

  const hasWarnings = requirement.warningMetadata && requirement.warningMetadata.length > 0;

  return (
    <div className={`requirement-card ${hasWarnings ? "has-review-warning" : ""}`}>
      {/* Header Row: Order Number, Name/Autocomplete, Badges, Reorder/Delete */}
      <div className="requirement-card-header">
        <div className="requirement-order-badge">#{index + 1}</div>

        <div className="requirement-main-label-area">
          {isEditingLabel ? (
            isSkillCategory ? (
              <TaxonomySkillAutocomplete
                initialValue={requirement.label}
                onSelectSkill={handleSelectTaxonomySkill}
                onUseCustomText={handleUseCustomText}
                autoFocus={!requirement.label.trim()}
                placeholder="Search O*NET skills or type custom skill..."
              />
            ) : (
              <div className="custom-req-input-wrapper">
                <input
                  type="text"
                  className="form-input"
                  placeholder={`Enter ${requirement.category.toLowerCase()} requirement...`}
                  value={requirement.label}
                  onChange={(e) => onChange({ ...requirement, label: e.target.value, origin: "RECRUITER_ENTERED", taxonomySkillConceptId: null })}
                  onBlur={() => {
                    if (requirement.label.trim()) setIsEditingLabel(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && requirement.label.trim()) {
                      setIsEditingLabel(false);
                    }
                  }}
                  autoFocus={!requirement.label.trim()}
                  aria-label="Requirement description"
                />
              </div>
            )
          ) : (
            <div className="requirement-label-display">
              <span className="requirement-title-text">{requirement.label}</span>
              {requirement.origin === "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED" ? (
                <span className="badge badge-onet-confirmed">O*NET Skill</span>
              ) : (
                <span className="badge badge-custom-entered">Custom</span>
              )}
              <button
                type="button"
                className="btn-icon-subtle"
                onClick={() => setIsEditingLabel(true)}
                aria-label={`Edit requirement ${requirement.label}`}
                title="Edit name"
              >
                <Icon name="edit" size={14} />
              </button>
            </div>
          )}
        </div>

        {/* Actionable "Reason required" chip */}
        {needsRationale && (
          <button
            type="button"
            className="actionable-rationale-prompt"
            onClick={handleFocusRationale}
            title="Add business reason for this required criterion"
          >
            <Icon name="alert-triangle" size={12} />
            <span>Reason suggested</span>
          </button>
        )}

        {/* Reordering and Delete Controls */}
        <div className="requirement-card-actions">
          <button
            type="button"
            className="btn-icon-control"
            disabled={index === 0}
            onClick={onMoveUp}
            aria-label={`Move requirement ${requirement.label || index + 1} up`}
            title="Move up"
          >
            <Icon name="chevron-left" size={14} style={{ transform: "rotate(90deg)" }} />
          </button>
          <button
            type="button"
            className="btn-icon-control"
            disabled={index === totalCount - 1}
            onClick={onMoveDown}
            aria-label={`Move requirement ${requirement.label || index + 1} down`}
            title="Move down"
          >
            <Icon name="chevron-down" size={14} />
          </button>
          <button
            type="button"
            className="btn-icon-control text-danger"
            onClick={onRemove}
            aria-label={`Remove requirement ${requirement.label || index + 1}`}
            title="Remove requirement"
          >
            <Icon name="trash" size={14} />
          </button>
        </div>
      </div>

      {/* Primary Configuration Grid */}
      <div className="requirement-primary-controls-grid">
        <div className="form-group-compact">
          <label htmlFor={`cat-${index}`} className="form-label-xs">Category</label>
          <select
            id={`cat-${index}`}
            className="form-select-sm"
            value={requirement.category}
            onChange={(e) => handleCategoryChange(e.target.value as RequirementCategory)}
          >
            <option value="SKILL">Skill</option>
            <option value="EXPERIENCE">Experience</option>
            <option value="RESPONSIBILITY">Responsibility</option>
            <option value="EDUCATION">Education</option>
            <option value="CERTIFICATION">Certification</option>
            <option value="LANGUAGE">Language</option>
            <option value="OTHER">Other</option>
          </select>
        </div>

        <div className="form-group-compact">
          <label htmlFor={`nec-${index}`} className="form-label-xs">Requirement Type</label>
          <select
            id={`nec-${index}`}
            className="form-select-sm"
            value={requirement.necessity}
            onChange={(e) =>
              onChange({ ...requirement, necessity: e.target.value as RequirementNecessity })
            }
          >
            <option value="MUST_HAVE">Required</option>
            <option value="PREFERRED">Preferred</option>
          </select>
        </div>

        <div className="form-group-compact">
          <label htmlFor={`prio-${index}`} className="form-label-xs">Priority</label>
          <select
            id={`prio-${index}`}
            className="form-select-sm"
            value={requirement.priority}
            onChange={(e) =>
              onChange({ ...requirement, priority: e.target.value as RequirementPriority })
            }
          >
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </div>

        <div className="form-group-compact">
          <label htmlFor={`exp-${index}`} className="form-label-xs">Min. Experience (Months)</label>
          <input
            id={`exp-${index}`}
            type="number"
            min={1}
            max={600}
            className="form-input-sm"
            placeholder="e.g. 24"
            value={requirement.minExperienceMonths ?? ""}
            onChange={(e) => {
              const val = e.target.value ? parseInt(e.target.value, 10) : null;
              onChange({ ...requirement, minExperienceMonths: val });
            }}
          />
        </div>
      </div>

      {/* Review Warnings Indicator */}
      {hasWarnings && (
        <div className="requirement-warning-banner" role="alert">
          <Icon name="alert-triangle" size={15} className="warning-icon" />
          <div className="warning-content">
            {requirement.warningMetadata?.map((w, wIdx) => (
              <p key={wIdx} className="warning-msg-text">
                {w.message}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Collapsed More Options Toggle */}
      <div className="requirement-advanced-toggle-row">
        <button
          type="button"
          className="advanced-toggle-btn"
          onClick={() => setShowMoreOptions(!showMoreOptions)}
          aria-expanded={showMoreOptions}
        >
          <Icon name={showMoreOptions ? "chevron-down" : "chevron-right"} size={13} />
          <span>More options (reason, recency, synonyms, evidence locations)</span>
        </button>
      </div>

      {/* Collapsed More Options Panel */}
      {showMoreOptions && (
        <div className="requirement-advanced-panel">
          {/* Plain Language Rationale */}
          <div className="form-group">
            <label htmlFor={`rat-${index}`} className="form-label-xs">
              Why is this required? <span className="text-muted">(Job-related reason)</span>
            </label>
            <textarea
              id={`rat-${index}`}
              ref={rationaleTextareaRef}
              className="form-textarea-sm"
              rows={2}
              placeholder="Why is this requirement necessary for this role?..."
              value={requirement.rationale ?? ""}
              onChange={(e) => onChange({ ...requirement, rationale: e.target.value })}
            />
          </div>

          <div className="advanced-two-col-grid">
            {/* Recency Input */}
            <div className="form-group-compact">
              <label htmlFor={`rec-${index}`} className="form-label-xs">
                How recently should it have been used? (Years)
              </label>
              <input
                id={`rec-${index}`}
                type="number"
                min={1}
                max={50}
                className="form-input-sm"
                placeholder="e.g. 3 (within last 3 years)"
                value={requirement.recencyYears ?? ""}
                onChange={(e) => {
                  const val = e.target.value ? parseInt(e.target.value, 10) : null;
                  onChange({ ...requirement, recencyYears: val });
                }}
              />
            </div>
          </div>

          {/* Accepted Equivalents Tag Editor */}
          <div className="form-group">
            <label htmlFor={`equiv-${index}`} className="form-label-xs">
              Accepted equivalent terms <span className="text-muted">(Alternative titles or synonyms)</span>
            </label>
            <div className="tag-input-row">
              <input
                id={`equiv-${index}`}
                type="text"
                className="form-input-sm"
                placeholder="Add synonym or alias..."
                value={equivalentInput}
                onChange={(e) => setEquivalentInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddEquivalent();
                  }
                }}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleAddEquivalent}
              >
                Add
              </button>
            </div>
            {requirement.acceptedEquivalents && requirement.acceptedEquivalents.length > 0 && (
              <div className="tag-pill-container">
                {requirement.acceptedEquivalents.map((eq, eqIdx) => (
                  <span key={eqIdx} className="tag-pill">
                    {eq}
                    <button
                      type="button"
                      className="tag-remove-btn"
                      onClick={() => handleRemoveEquivalent(eq)}
                      aria-label={`Remove equivalent ${eq}`}
                    >
                      <Icon name="x" size={11} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Accepted Evidence Types Checkboxes */}
          <div className="form-group">
            <label className="form-label-xs">Where can this be shown?</label>
            <div className="evidence-checkboxes-grid">
              {ALL_EVIDENCE_TYPES.map(({ type, label }) => {
                const checked = (requirement.acceptedEvidenceTypes || []).includes(type);
                return (
                  <label key={type} className="checkbox-item-label">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => handleToggleEvidenceType(type)}
                    />
                    <span>{label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
