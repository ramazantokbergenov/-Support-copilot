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
}

export interface TicketDetail extends TicketSummary {
  message: string;
  attachments: TicketAttachment[];
  extracted_facts: string[] | null;
  matched_rules: RuleRecord[];
  draft_reply: string | null;
  escalation_reason: string | null;
  ai_analysis: AiAnalysis | null;
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
