-- Run once in YOUR Supabase project's SQL editor. No participant data is included.
create table if not exists public.qp_cases (
  id text primary key, version integer not null, payload jsonb not null
);
create table if not exists public.qp_ai_usage (
  day date primary key, calls integer not null default 0
);
alter table public.qp_cases enable row level security;
alter table public.qp_ai_usage enable row level security;
revoke all on public.qp_cases, public.qp_ai_usage from anon, authenticated;
grant all on public.qp_cases, public.qp_ai_usage to service_role;

create or replace function public.qp_save_case(p_id text, p_expected integer, p_payload jsonb)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare updated jsonb;
begin
  if p_expected is null then
    insert into qp_cases values(p_id, 0, p_payload) returning payload into updated;
  else
    update qp_cases set version=p_expected+1, payload=p_payload
      where id=p_id and version=p_expected returning payload into updated;
    if updated is null then raise exception 'QP_CONFLICT'; end if;
  end if;
  return updated;
end $$;

create or replace function public.qp_claim_case(p_now double precision)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare picked qp_cases; updated jsonb;
begin
  select * into picked from qp_cases where
    (payload->>'state'='queued' and coalesce((payload->>'next_attempt')::double precision,0)<=p_now)
    or (payload->>'state'='processing' and coalesce((payload->>'lease_until')::double precision,0)<p_now)
    order by id for update skip locked limit 1;
  if not found then return null; end if;
  updated := picked.payload || jsonb_build_object('state','processing','lease_until',p_now+1800,
      'version',picked.version+1,'attempts',coalesce((picked.payload->>'attempts')::integer,0)+1,'updated_at',p_now);
  update qp_cases set version=picked.version+1,payload=updated where id=picked.id;
  return updated;
end $$;

create or replace function public.qp_reserve_call(p_day date, p_limit integer)
returns boolean language plpgsql security invoker set search_path = public as $$
declare affected integer;
begin
  insert into qp_ai_usage values(p_day,0) on conflict do nothing;
  update qp_ai_usage set calls=calls+1 where day=p_day and calls<p_limit;
  get diagnostics affected = row_count;
  return affected=1;
end $$;
revoke execute on function public.qp_save_case(text,integer,jsonb), public.qp_claim_case(double precision), public.qp_reserve_call(date,integer) from public, anon, authenticated;
grant execute on function public.qp_save_case(text,integer,jsonb), public.qp_claim_case(double precision), public.qp_reserve_call(date,integer) to service_role;

insert into storage.buckets(id,name,public,file_size_limit)
values('quayproof-documents','quayproof-documents',false,10485760)
on conflict(id) do nothing;
-- No public storage policies: backend uses its server-only service-role key.
