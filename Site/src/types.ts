export type TicketStatus =
  | "New"
  | "Processing"
  | "Needs Review"
  | "Approved"
  | "Escalated"
  | "Closed";

export type TicketPriority = "Low" | "Normal" | "High" | "Urgent";

export interface TicketSummary {
  ticket_id: string;
  player_id: string;
  category: string | null;
  priority: TicketPriority;
  status: TicketStatus;
  confidence: number | null;
  escalation_required: boolean | null;
  created_at: string;
  language?: string | null;
  summary?: string | null;
}

export interface TicketAttachment {
  attachment_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface RuleRecord {
  document_name: string;
  rule_id: string;
  rule_title: string;
  rule_text: string;
  source_url: string;
  language: string;
  version_or_date: string | null;
}

export interface AnalysisAttachment extends TicketAttachment {
  inspected: boolean;
}

export interface AiAnalysis {
  category: string;
  category_reason: string;
  language: string;
  summary: string;
  player_claims: string[];
  attachments: AnalysisAttachment[];
  verified_system_data: string[];
  unknowns: string[];
  matched_rules: Array<RuleRecord>;
  draft_reply: string;
  confidence: number;
  escalation_required: boolean;
  escalation_reason: string | null;
  priority?: string;
  provided_evidence?: AnalysisAttachment[];
  missing_information_questions?: string[];
  escalation_reasons?: string[];
  human_review_required?: boolean;
}

export interface TicketDetail extends TicketSummary {
  message: string;
  attachments: TicketAttachment[];
  extracted_facts: string[] | null;
  matched_rules: RuleRecord[];
  draft_reply: string | null;
  draft_id?: string | null;
  draft_version?: number | null;
  draft_status?: string | null;
  escalation_reason: string | null;
  ai_analysis: AiAnalysis | null;
  operator_notes?: OperatorNote[];
}

export interface TicketListResponse {
  items: TicketSummary[];
  count: number;
  limit: number;
  offset: number;
}

export interface StructuredAnalysisResult {
  ticket_id: string;
  language: "ru" | "kk" | "uz" | "other";
  category: "appeal_ban" | "player_report" | "admin_complaint" | "account_security" | "payment" | "bug" | "other";
  priority: "low" | "normal" | "high" | "urgent";
  summary: string;
  player_claims: string[];
  provided_evidence: TicketAttachment[];
  verified_data: string[];
  unknowns: string[];
  missing_information_questions: string[];
  rule_references: OfficialRuleReference[];
  analysis: string;
  draft_reply: string;
  human_review_required: boolean;
  escalation_reasons: string[];
  confidence: number;
}

export interface OfficialRuleReference {
  document_title: string;
  rule_number: string;
  exact_excerpt: string;
  source_url: string;
  source_version_date: string;
}

export interface DraftRecord {
  id: string;
  ticket_id: string;
  body: string;
  status: string;
  version: number;
  created_at: string;
}

export interface OperatorNote {
  id: string;
  operator_id: string;
  body: string;
  created_at: string;
}

export interface OperatorEvent {
  id: string;
  operator_id: string | null;
  action: string;
  old_value: unknown;
  new_value: unknown;
  created_at: string;
}

export interface RuleList {
  items: RuleRecord[];
  count: number;
}

export interface CreateTicketInput {
  player_id: string;
  message: string;
  category?: string;
  priority: TicketPriority;
  attachments: File[];
}

export interface TicketQuery {
  q?: string;
  status?: TicketStatus | "";
  priority?: TicketPriority | "";
  category?: string;
  limit?: number;
  offset?: number;
}
