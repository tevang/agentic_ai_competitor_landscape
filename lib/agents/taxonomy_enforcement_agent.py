"""Controlled ontology/taxonomy enforcement for verified company-step links."""

from lib.config import AppConfig
from lib.models import CompanyProfile, PipelineStep, TaxonomyAssignment
from lib.retrieval.evidence_store import EvidenceStore
from lib.taxonomy.schema import format_taxonomy_target_for_step, get_step_taxonomy_payload
from lib.utils.text_utils import unique_preserve_order


class TaxonomyEnforcementAgent:
    """Force verified company-step links into a controlled taxonomy before analysis."""

    def __init__(self, config: AppConfig, store: EvidenceStore) -> None:
        """Store configuration and persistence dependencies for taxonomy enforcement."""

        self.config = config
        self.store = store

    def map_step(self, step: PipelineStep) -> TaxonomyAssignment:
        """Map a pipeline step to the controlled canonical taxonomy."""

        payload = get_step_taxonomy_payload(step.phase, step.step)
        return TaxonomyAssignment(**payload)

    def format_target(self, step: PipelineStep) -> str:
        """Return a readable taxonomy target string for planner and verifier prompts."""

        return format_taxonomy_target_for_step(step.phase, step.step)

    def apply_step_taxonomy(self, profile: CompanyProfile, assignment: TaxonomyAssignment) -> CompanyProfile:
        """Apply a controlled taxonomy assignment to a company profile and persist the update."""

        if not self.config.taxonomy.enforce:
            return profile

        if assignment.primary_phase and not profile.taxonomy_primary_phase:
            profile.taxonomy_primary_phase = assignment.primary_phase

        if assignment.primary_subcategory and not profile.taxonomy_primary_subcategory:
            profile.taxonomy_primary_subcategory = assignment.primary_subcategory

        profile.taxonomy_phase_labels = unique_preserve_order(
            profile.taxonomy_phase_labels + assignment.phase_labels
        )
        profile.taxonomy_subcategory_labels = unique_preserve_order(
            profile.taxonomy_subcategory_labels + assignment.subcategory_labels
        )

        self.store.save_company_profile(profile)
        return profile