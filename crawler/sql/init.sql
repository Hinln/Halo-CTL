create table if not exists crawl_runs (
  id bigserial primary key,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  notes text
);

create table if not exists pages (
  id bigserial primary key,
  source_url text not null,
  domain text not null,
  url_path text not null,
  kind text not null,
  title text,
  slug text,
  author text,
  published_at timestamptz,
  updated_at timestamptz,
  categories text[] not null default '{}',
  tags text[] not null default '{}',
  content_html text,
  content_text text,
  fetched_at timestamptz not null default now(),
  etag text,
  last_modified text,
  http_status int,
  constraint pages_source_url_uk unique (source_url)
);

create index if not exists pages_domain_idx on pages (domain);
create index if not exists pages_kind_idx on pages (kind);

create table if not exists api_endpoints (
  id bigserial primary key,
  source_url text not null,
  domain text not null,
  api_path text not null,
  http_method text not null,
  summary text,
  request_example text,
  response_example text,
  status_codes jsonb,
  fetched_at timestamptz not null default now(),
  constraint api_endpoints_source_url_uk unique (source_url)
);

create index if not exists api_endpoints_path_idx on api_endpoints (api_path);

create table if not exists crawl_queue (
  id bigserial primary key,
  source_url text not null,
  domain text not null,
  status text not null,
  depth int not null default 0,
  discovered_at timestamptz not null default now(),
  last_attempt_at timestamptz,
  attempts int not null default 0,
  constraint crawl_queue_source_url_uk unique (source_url)
);

create index if not exists crawl_queue_status_idx on crawl_queue (status);

create table if not exists api_validation_results (
  id bigserial primary key,
  run_id bigint references crawl_runs(id) on delete cascade,
  checked_at timestamptz not null default now(),
  url text not null,
  method text not null,
  params jsonb,
  status int,
  ok boolean not null,
  error text,
  response_body text
);

create index if not exists api_validation_results_run_idx on api_validation_results (run_id);

