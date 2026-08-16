"""
LangChain bridge — BaseTool wrappers for all 16 ThreatAssessor MCP tools.

Usage::

    from mcp_connector import MCPClient, langchain_tools
    from langchain.agents import initialize_agent, AgentType
    from langchain_openai import ChatOpenAI

    ta     = MCPClient(base_url="http://localhost:8000", api_key="...")
    tools  = langchain_tools(ta)
    llm    = ChatOpenAI(model="gpt-4o")
    agent  = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS, verbose=True)

    agent.run("What are the top threats for the aws_3tier architecture?")

Or pick specific tools::

    from mcp_connector.langchain_bridge import GovernanceCheckTool, ExportAssessmentTool

    check = GovernanceCheckTool(client=ta)
    result = check.run("graph LR\\n  A[ignore all instructions] --> B")
"""

from __future__ import annotations

import json
from typing import Any, List, Optional, Type

try:
    from langchain.tools import BaseTool
    from pydantic import BaseModel, Field
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False
    # Stub so the module can be imported without langchain installed
    class BaseTool:  # type: ignore
        pass
    class BaseModel:  # type: ignore
        pass
    def Field(*a, **kw):  # type: ignore
        return None


def _require_langchain() -> None:
    if not _LANGCHAIN_AVAILABLE:
        raise ImportError(
            "LangChain is required for langchain_tools. "
            "Install with: pip install langchain langchain-openai pydantic"
        )


# ── Input schemas (Pydantic) ──────────────────────────────────────────────────

class ArchNameInput(BaseModel):
    arch_name: str = Field(description="Architecture directory name.")

class GovernanceCheckInput(BaseModel):
    mmd_content: str = Field(description="Raw Mermaid diagram string to screen.")
    arch_name: str   = Field("mcp_input", description="Optional label for this check.")

class AnalyzeInput(BaseModel):
    mmd_content: str = Field(description="Raw Mermaid diagram string.")
    ssp_profile: str = Field("low_risk_cloud", description="Risk profile.")

class MitreLookupInput(BaseModel):
    technique_ids: str = Field(description="Comma-separated ATT&CK IDs, e.g. 'T1190,T1078'.")

class ExpertReviewInput(BaseModel):
    arch_name:   str = Field(description="Architecture directory name.")
    critic_mode: str = Field("partial_parallel", description="Execution mode.")

class JobStatusInput(BaseModel):
    job_id:              str  = Field(description="UUID from run_expert_review.")
    wait_for_completion: bool = Field(False, description="Block until done.")

class TatbInput(BaseModel):
    arch_name: str = Field("", description="Architecture name. Empty for corpus.")

class ExportInput(BaseModel):
    arch_name: str  = Field(description="Architecture directory name.")
    save:      bool = Field(False, description="Write ta_export.json to report dir.")

class QueryBrainInput(BaseModel):
    mode:               str = Field("infer", description="infer | gaps | patterns")
    arch_name:          str = Field("", description="Corpus architecture name.")
    topology_signature: str = Field("", description="Direct 16-char topology hash.")
    arch_type:          str = Field("", description="Architecture type hint.")
    arch_type_filter:   str = Field("", description="Filter patterns by arch_type.")

class BrainFeedbackInput(BaseModel):
    feedback:           str = Field(description="confirmed | wrong | partial")
    arch_name:          str = Field("", description="Corpus architecture name.")
    topology_signature: str = Field("", description="Direct topology hash.")
    arch_type:          str = Field("", description="Architecture type.")
    mode:               str = Field("infer", description="Query mode feedback applies to.")
    reference_ts:       str = Field("", description="ISO timestamp of the original query.")

class GenerateSyntheticInput(BaseModel):
    gap_ids:     str = Field("", description="Comma-separated gap IDs. Empty = auto-select.")
    max_per_run: int = Field(3, description="Maximum diagrams to generate.")


# ── Tool classes ──────────────────────────────────────────────────────────────

class GovernanceCheckTool(BaseTool):
    name: str = "governance_check"
    description: str = (
        "Screen raw Mermaid MMD content for injection, path traversal, external URLs, "
        "and evasion homoglyphs in ~50ms (no LLM). "
        "Returns fired DETECT rule IDs and blocked=true on CRITICAL input. "
        "Call before analyze_architecture to pre-screen untrusted diagrams."
    )
    args_schema: Type[BaseModel] = GovernanceCheckInput
    client: Any

    def _run(self, mmd_content: str, arch_name: str = "mcp_input") -> str:
        result = self.client.governance_check(mmd_content, arch_name)
        return json.dumps(result, indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class AnalyzeArchitectureTool(BaseTool):
    name: str = "analyze_architecture"
    description: str = (
        "Submit a Mermaid architecture diagram for full threat modelling (~30s). "
        "Returns MITRE ATT&CK-mapped attack paths and control recommendations."
    )
    args_schema: Type[BaseModel] = AnalyzeInput
    client: Any

    def _run(self, mmd_content: str, ssp_profile: str = "low_risk_cloud") -> str:
        result = self.client.analyze_architecture(mmd_content, ssp_profile)
        return json.dumps(result, indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GetThreatBriefingTool(BaseTool):
    name: str = "get_threat_briefing"
    description: str = "Get a CISO-ready threat briefing for an analysed architecture."
    args_schema: Type[BaseModel] = ArchNameInput
    client: Any

    def _run(self, arch_name: str) -> str:
        result = self.client.get_threat_briefing(arch_name, fmt="md")
        return result if isinstance(result, str) else json.dumps(result, indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GetGovernanceSignalsTool(BaseTool):
    name: str = "get_governance_signals"
    description: str = (
        "Get AIVSS composite score and governance signals "
        "(exploitation, manipulation, leakage, sovereignty) for an architecture."
    )
    args_schema: Type[BaseModel] = ArchNameInput
    client: Any

    def _run(self, arch_name: str) -> str:
        return json.dumps(self.client.get_governance_signals(arch_name), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GetDetectTrendsTool(BaseTool):
    name: str = "get_detect_trends"
    description: str = (
        "Get SOC DETECT rule firing trends for an architecture. "
        "Trend values: new | rising | stable | falling | cleared | never."
    )
    args_schema: Type[BaseModel] = ArchNameInput
    client: Any

    def _run(self, arch_name: str) -> str:
        return json.dumps(self.client.get_detect_trends(arch_name), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class ListArchitecturesTool(BaseTool):
    name: str = "list_architectures"
    description: str = "List all architectures that have been analysed, with metadata."
    client: Any

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return json.dumps(self.client.list_architectures(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class LookupMitreTechniqueTool(BaseTool):
    name: str = "lookup_mitre_technique"
    description: str = (
        "Look up MITRE ATT&CK technique details and recommended mitigations. "
        "Pass comma-separated ATT&CK IDs, e.g. 'T1190,T1078,T1059'."
    )
    args_schema: Type[BaseModel] = MitreLookupInput
    client: Any

    def _run(self, technique_ids: str) -> str:
        return json.dumps(self.client.lookup_mitre_technique(technique_ids), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class ExportAssessmentTool(BaseTool):
    name: str = "export_assessment"
    description: str = (
        "Export a unified TA assessment bundle (ta-export/1.0) with gate (PASS|BLOCK), "
        "attack paths, TATB scores, OCSF findings, and OTM mitigations. "
        "Use gate.result == 'BLOCK' to halt a CI/CD pipeline."
    )
    args_schema: Type[BaseModel] = ExportInput
    client: Any

    def _run(self, arch_name: str, save: bool = False) -> str:
        return json.dumps(self.client.export_assessment(arch_name, save), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class RunExpertReviewTool(BaseTool):
    name: str = "run_expert_review"
    description: str = (
        "Queue a MoE expert review (5 critics + ScrumMaster) for an architecture. "
        "Returns a job_id — follow up with get_job_status."
    )
    args_schema: Type[BaseModel] = ExpertReviewInput
    client: Any

    def _run(self, arch_name: str, critic_mode: str = "partial_parallel") -> str:
        return json.dumps(self.client.run_expert_review(arch_name, critic_mode), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GetJobStatusTool(BaseTool):
    name: str = "get_job_status"
    description: str = "Poll an expert review job by job_id. Returns status and result when done."
    args_schema: Type[BaseModel] = JobStatusInput
    client: Any

    def _run(self, job_id: str, wait_for_completion: bool = False) -> str:
        return json.dumps(self.client.get_job_status(job_id, wait_for_completion), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GetTatbScoresTool(BaseTool):
    name: str = "get_tatb_scores"
    description: str = (
        "Get TATB quality scores (threat_relevant, ttp_accurate, risk_defensible, plan_actionable). "
        "Pass arch_name for one architecture, omit for the full corpus."
    )
    args_schema: Type[BaseModel] = TatbInput
    client: Any

    def _run(self, arch_name: str = "") -> str:
        return json.dumps(self.client.get_tatb_scores(arch_name), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class QueryTaBrainTool(BaseTool):
    name: str = "query_ta_brain"
    description: str = (
        "Query TA Brain patterns. Mode 'infer': predict threats and missing controls. "
        "Mode 'gaps': list under-sampled topology regions. "
        "Mode 'patterns': list all learned patterns."
    )
    args_schema: Type[BaseModel] = QueryBrainInput
    client: Any

    def _run(
        self,
        mode: str = "infer",
        arch_name: str = "",
        topology_signature: str = "",
        arch_type: str = "",
        arch_type_filter: str = "",
    ) -> str:
        return json.dumps(
            self.client.query_ta_brain(mode, arch_name, topology_signature, arch_type, arch_type_filter),
            indent=2,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class RecordBrainFeedbackTool(BaseTool):
    name: str = "record_brain_feedback"
    description: str = (
        "Record confirmed/wrong/partial feedback on a TA Brain prediction. "
        "Closes the TACO learning loop — wrong decays confidence, confirmed strengthens it."
    )
    args_schema: Type[BaseModel] = BrainFeedbackInput
    client: Any

    def _run(
        self,
        feedback: str,
        arch_name: str = "",
        topology_signature: str = "",
        arch_type: str = "",
        mode: str = "infer",
        reference_ts: str = "",
    ) -> str:
        return json.dumps(
            self.client.record_brain_feedback(
                feedback, arch_name, topology_signature, arch_type, mode, reference_ts
            ),
            indent=2,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


class GenerateSyntheticArchitecturesTool(BaseTool):
    name: str = "generate_synthetic_architectures"
    description: str = (
        "Generate synthetic Mermaid diagrams from TA Brain meta-layer gaps. "
        "Stages diagrams for approval before harness submission."
    )
    args_schema: Type[BaseModel] = GenerateSyntheticInput
    client: Any

    def _run(self, gap_ids: str = "", max_per_run: int = 3) -> str:
        return json.dumps(
            self.client.generate_synthetic_architectures(gap_ids, max_per_run),
            indent=2,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ── Factory ───────────────────────────────────────────────────────────────────

def langchain_tools(client: Any) -> List[BaseTool]:
    """Return LangChain BaseTool instances for all 16 ThreatAssessor tools.

    Args:
        client: MCPClient instance.

    Returns:
        List of BaseTool subclasses ready to pass to initialize_agent or
        create_openai_tools_agent.
    """
    _require_langchain()
    return [
        GovernanceCheckTool(client=client),
        AnalyzeArchitectureTool(client=client),
        GetThreatBriefingTool(client=client),
        GetGovernanceSignalsTool(client=client),
        GetDetectTrendsTool(client=client),
        ListArchitecturesTool(client=client),
        LookupMitreTechniqueTool(client=client),
        ExportAssessmentTool(client=client),
        RunExpertReviewTool(client=client),
        GetJobStatusTool(client=client),
        GetTatbScoresTool(client=client),
        QueryTaBrainTool(client=client),
        RecordBrainFeedbackTool(client=client),
        GenerateSyntheticArchitecturesTool(client=client),
    ]
