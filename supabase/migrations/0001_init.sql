-- Coverse schema.
--
-- Yjs updates are stored as an append-only log rather than a single blob, so
-- concurrent writers never clobber each other and a document can be rebuilt by
-- replaying the log. The backend compacts the log periodically.

create table if not exists public.documents (
    id           uuid primary key default gen_random_uuid(),
    owner_id     uuid not null references auth.users (id) on delete cascade,
    title        text not null default 'Untitled',
    mode         text not null default 'doc' check (mode in ('doc', 'canvas')),
    -- "editor" is the anyone-with-the-link behaviour people expect from a
    -- collaborative editor; "none" restricts access to the owner and invitees.
    link_access  text not null default 'editor' check (link_access in ('editor', 'none')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists public.document_collaborators (
    id           bigserial primary key,
    document_id  uuid not null references public.documents (id) on delete cascade,
    user_id      uuid not null references auth.users (id) on delete cascade,
    role         text not null default 'editor' check (role in ('editor', 'viewer')),
    created_at   timestamptz not null default now(),
    unique (document_id, user_id)
);

create table if not exists public.document_updates (
    id           bigserial primary key,
    document_id  uuid not null references public.documents (id) on delete cascade,
    update       bytea not null,
    created_at   timestamptz not null default now()
);

create table if not exists public.chat_messages (
    id           bigserial primary key,
    document_id  uuid not null references public.documents (id) on delete cascade,
    user_id      uuid not null,
    role         text not null check (role in ('user', 'assistant')),
    content      text not null,
    provider     text not null default '',
    model        text not null default '',
    created_at   timestamptz not null default now()
);

create index if not exists ix_documents_owner on public.documents (owner_id);
create index if not exists ix_document_updates_doc on public.document_updates (document_id, id);
create index if not exists ix_collaborators_user on public.document_collaborators (user_id);
create index if not exists ix_chat_messages_doc on public.chat_messages (document_id, id);

-- Keep updated_at honest, so the document list orders by real activity.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists documents_touch_updated_at on public.documents;
create trigger documents_touch_updated_at
    before update on public.documents
    for each row execute function public.touch_updated_at();

-- --- Row level security -----------------------------------------------------
--
-- The Python backend connects with the service role key and enforces access
-- itself, because the websocket layer cannot go through PostgREST. These
-- policies protect anything that reaches the database as an end user.

alter table public.documents enable row level security;
alter table public.document_collaborators enable row level security;
alter table public.document_updates enable row level security;
alter table public.chat_messages enable row level security;

-- Defined as a security definer function to avoid the policies on documents and
-- document_collaborators referring to each other in a loop.
create or replace function public.can_access_document(doc_id uuid, uid uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1 from public.documents d
        where d.id = doc_id
          and (
              d.owner_id = uid
              or d.link_access <> 'none'
              or exists (
                  select 1 from public.document_collaborators c
                  where c.document_id = d.id and c.user_id = uid
              )
          )
    );
$$;

drop policy if exists documents_select on public.documents;
create policy documents_select on public.documents
    for select using (public.can_access_document(id, auth.uid()));

drop policy if exists documents_insert on public.documents;
create policy documents_insert on public.documents
    for insert with check (owner_id = auth.uid());

drop policy if exists documents_update on public.documents;
create policy documents_update on public.documents
    for update using (public.can_access_document(id, auth.uid()));

-- Deletion stays with the owner: link access must never imply ownership.
drop policy if exists documents_delete on public.documents;
create policy documents_delete on public.documents
    for delete using (owner_id = auth.uid());

drop policy if exists collaborators_select on public.document_collaborators;
create policy collaborators_select on public.document_collaborators
    for select using (public.can_access_document(document_id, auth.uid()));

drop policy if exists collaborators_write on public.document_collaborators;
create policy collaborators_write on public.document_collaborators
    for all using (
        exists (
            select 1 from public.documents d
            where d.id = document_id and d.owner_id = auth.uid()
        )
    );

drop policy if exists updates_access on public.document_updates;
create policy updates_access on public.document_updates
    for all using (public.can_access_document(document_id, auth.uid()));

drop policy if exists chat_access on public.chat_messages;
create policy chat_access on public.chat_messages
    for all using (public.can_access_document(document_id, auth.uid()));
