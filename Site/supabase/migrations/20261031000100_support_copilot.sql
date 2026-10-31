create extension if not exists vector with schema extensions;

create type public.operator_role as enum ('support_operator', 'admin');
create type public.ticket_status as enum (
  'New',
  'Processing',
  'Needs Review',
  'Approved',
  'Escalated',
  'Closed'
);
create type public.ticket_priority as enum ('Low', 'Normal', 'High', 'Urgent');

create table public.operator_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default '',
  role public.operator_role not null default 'support_operator',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  ticket_id text not null unique,
  player_id text not null check (char_length(player_id) between 1 and 128),
  language text,
  category text,
  priority public.ticket_priority not null default 'Normal',
  summary text,
  original_message text not null check (char_length(original_message) between 1 and 20000),
  status public.ticket_status not null default 'New',
  human_review_required boolean not null default false,
  escalation_reasons text[] not null default '{}',
  confidence numeric(4, 3) check (confidence between 0 and 1),
  created_by uuid references auth.users (id) on delete set null,
  assigned_operator_id uuid references public.operator_profiles (user_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.rule_documents (
  id uuid primary key default gen_random_uuid(),
  document_title text not null,
  source_url text not null check (source_url ~ '^https?://'),
  source_version_date text,
  content text not null,
  is_active boolean not null default false,
  verified_by text,
  check (not is_active or verified_by is not null),
  created_at timestamptz not null default now()
);

create table public.rule_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.rule_documents (id) on delete cascade,
  rule_number text not null,
  content text not null,
  embedding extensions.vector(1536),
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  unique (document_id, rule_number)
);

create table public.ticket_analysis (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  player_claims jsonb not null default '[]',
  provided_evidence jsonb not null default '[]',
  verified_data jsonb not null default '[]',
  unknowns jsonb not null default '[]',
  missing_information_questions jsonb not null default '[]',
  analysis jsonb not null default '{}',
  draft_reply text,
  model_name text not null,
  created_at timestamptz not null default now()
);

create table public.ticket_rule_references (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  document_id uuid not null references public.rule_documents (id) on delete restrict,
  rule_number text not null,
  exact_excerpt text not null,
  source_url text not null,
  source_version_date text,
  created_at timestamptz not null default now(),
  foreign key (document_id, rule_number)
    references public.rule_chunks (document_id, rule_number) on delete restrict,
  unique (ticket_id, document_id, rule_number)
);

create table public.ticket_attachments (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  file_path text not null unique,
  file_type text not null,
  original_filename text not null,
  size_bytes bigint not null check (size_bytes between 0 and 10485760),
  uploaded_at timestamptz not null default now()
);

create table public.ticket_reply_drafts (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  source_analysis_id uuid references public.ticket_analysis (id) on delete set null,
  body text not null check (char_length(body) between 1 and 20000),
  version integer not null check (version > 0),
  status text not null default 'pending_review'
    check (status in ('pending_review', 'reviewed', 'approved', 'rejected')),
  created_by uuid references auth.users (id) on delete set null,
  updated_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ticket_id, version)
);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid references public.tickets (id) on delete set null,
  operator_id uuid references public.operator_profiles (user_id) on delete set null,
  action text not null check (char_length(action) between 1 and 100),
  old_value jsonb,
  new_value jsonb,
  created_at timestamptz not null default now()
);

create table public.operator_notes (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  operator_id uuid not null references public.operator_profiles (user_id) on delete cascade,
  body text not null check (char_length(body) between 1 and 5000),
  created_at timestamptz not null default now()
);

create index tickets_created_at_idx on public.tickets (created_at desc);
create index tickets_status_priority_idx on public.tickets (status, priority);
create index tickets_assigned_operator_idx on public.tickets (assigned_operator_id);
create index ticket_analysis_ticket_created_idx
  on public.ticket_analysis (ticket_id, created_at desc);
create index ticket_rule_references_ticket_idx
  on public.ticket_rule_references (ticket_id);
create index operator_notes_ticket_created_idx
  on public.operator_notes (ticket_id, created_at desc);
create index rule_documents_active_idx on public.rule_documents (is_active);
create index rule_chunks_embedding_idx on public.rule_chunks
  using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger operator_profiles_touch_updated_at
  before update on public.operator_profiles
  for each row execute function public.touch_updated_at();
create trigger tickets_touch_updated_at
  before update on public.tickets
  for each row execute function public.touch_updated_at();
create trigger reply_drafts_touch_updated_at
  before update on public.ticket_reply_drafts
  for each row execute function public.touch_updated_at();

create or replace function public.is_support_operator()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.operator_profiles profile
    where profile.user_id = (select auth.uid())
      and profile.role in ('support_operator', 'admin')
  );
$$;

create or replace function public.match_rule_chunks(
  query_embedding extensions.vector(1536),
  match_threshold real default 0.35,
  match_count integer default 10,
  filter_language text default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  document_title text,
  source_url text,
  source_version_date text,
  rule_number text,
  content text,
  metadata jsonb,
  similarity real
)
language sql
stable
set search_path = ''
as $$
  select
    chunk.id,
    document.id,
    document.document_title,
    document.source_url,
    document.source_version_date,
    chunk.rule_number,
    chunk.content,
    chunk.metadata,
    (1 - (chunk.embedding OPERATOR(extensions.<=>) query_embedding))::real
  from public.rule_chunks chunk
  join public.rule_documents document on document.id = chunk.document_id
  where document.is_active
    and chunk.embedding is not null
    and (
      filter_language is null
      or lower(coalesce(chunk.metadata ->> 'language', '')) = lower(filter_language)
    )
    and (1 - (chunk.embedding OPERATOR(extensions.<=>) query_embedding)) >= match_threshold
  order by chunk.embedding OPERATOR(extensions.<=>) query_embedding
  limit greatest(1, least(match_count, 50));
$$;

create or replace function public.activate_rule_document(target_document_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_title text;
begin
  select document_title into target_title
  from public.rule_documents
  where id = target_document_id and verified_by is not null;
  if target_title is null then
    raise exception 'Verified rule document not found';
  end if;

  update public.rule_documents
  set is_active = false
  where document_title = target_title and is_active;
  update public.rule_documents
  set is_active = true
  where id = target_document_id;
end;
$$;

revoke all on function public.is_support_operator() from public, anon;
grant execute on function public.is_support_operator() to authenticated, service_role;
revoke all on function public.match_rule_chunks(
  extensions.vector(1536), real, integer, text
) from public, anon;
grant execute on function public.match_rule_chunks(
  extensions.vector(1536), real, integer, text
) to authenticated, service_role;
revoke all on function public.activate_rule_document(uuid) from public, anon, authenticated;
grant execute on function public.activate_rule_document(uuid) to service_role;

alter table public.operator_profiles enable row level security;
alter table public.tickets enable row level security;
alter table public.ticket_analysis enable row level security;
alter table public.rule_documents enable row level security;
alter table public.rule_chunks enable row level security;
alter table public.ticket_rule_references enable row level security;
alter table public.ticket_attachments enable row level security;
alter table public.ticket_reply_drafts enable row level security;
alter table public.audit_logs enable row level security;
alter table public.operator_notes enable row level security;

create policy "operators read own profile"
  on public.operator_profiles for select to authenticated
  using (user_id = (select auth.uid()) and public.is_support_operator());
create policy "operators read tickets"
  on public.tickets for select to authenticated
  using (public.is_support_operator());
create policy "operators read ticket analyses"
  on public.ticket_analysis for select to authenticated
  using (public.is_support_operator());
create policy "operators read active rule documents"
  on public.rule_documents for select to authenticated
  using (public.is_support_operator() and is_active);
create policy "operators read chunks of active rules"
  on public.rule_chunks for select to authenticated
  using (
    public.is_support_operator()
    and exists (
      select 1 from public.rule_documents document
      where document.id = document_id and document.is_active
    )
  );
create policy "operators read ticket rule references"
  on public.ticket_rule_references for select to authenticated
  using (public.is_support_operator());
create policy "operators read ticket attachments"
  on public.ticket_attachments for select to authenticated
  using (public.is_support_operator());
create policy "operators read reply drafts"
  on public.ticket_reply_drafts for select to authenticated
  using (public.is_support_operator());
create policy "operators read audit logs"
  on public.audit_logs for select to authenticated
  using (public.is_support_operator());
create policy "operators read notes"
  on public.operator_notes for select to authenticated
  using (public.is_support_operator());

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'ticket-evidence',
  'ticket-evidence',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'text/plain']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "operators read ticket evidence objects"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'ticket-evidence'
    and public.is_support_operator()
    and exists (
      select 1
      from public.ticket_attachments attachment
      join public.tickets ticket on ticket.id = attachment.ticket_id
      where attachment.file_path = name
    )
  );
