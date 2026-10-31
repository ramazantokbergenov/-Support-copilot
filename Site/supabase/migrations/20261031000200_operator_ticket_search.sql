create or replace function public.search_operator_tickets(
  search_query text,
  filter_status text,
  filter_priority text,
  filter_category text,
  page_limit integer,
  page_offset integer
)
returns table (
  ticket_id text,
  player_id text,
  category text,
  priority public.ticket_priority,
  status public.ticket_status,
  confidence numeric,
  human_review_required boolean,
  created_at timestamptz
)
language sql
stable
set search_path = ''
as $$
  select
    ticket.ticket_id,
    ticket.player_id,
    ticket.category,
    ticket.priority,
    ticket.status,
    ticket.confidence,
    ticket.human_review_required,
    ticket.created_at
  from public.tickets as ticket
  where (
    strpos(lower(ticket.ticket_id), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(ticket.player_id), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(ticket.original_message), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(coalesce(ticket.category, '')), lower(coalesce(search_query, ''))) > 0
  )
    and (filter_status is null or ticket.status::text = filter_status)
    and (filter_priority is null or ticket.priority::text = filter_priority)
    and (filter_category is null or ticket.category = filter_category)
  order by ticket.created_at desc, ticket.ticket_id
  limit greatest(1, least(coalesce(page_limit, 50), 100))
  offset greatest(coalesce(page_offset, 0), 0);
$$;

create or replace function public.count_operator_tickets(
  search_query text,
  filter_status text,
  filter_priority text,
  filter_category text
)
returns bigint
language sql
stable
set search_path = ''
as $$
  select count(*)
  from public.tickets as ticket
  where (
    strpos(lower(ticket.ticket_id), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(ticket.player_id), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(ticket.original_message), lower(coalesce(search_query, ''))) > 0
    or strpos(lower(coalesce(ticket.category, '')), lower(coalesce(search_query, ''))) > 0
  )
    and (filter_status is null or ticket.status::text = filter_status)
    and (filter_priority is null or ticket.priority::text = filter_priority)
    and (filter_category is null or ticket.category = filter_category);
$$;

revoke all on function public.search_operator_tickets(text, text, text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.search_operator_tickets(text, text, text, text, integer, integer)
  to service_role;
revoke all on function public.count_operator_tickets(text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.count_operator_tickets(text, text, text, text)
  to service_role;