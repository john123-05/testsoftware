-- Paper roll capacity per machine. PrintCount.txt counts printed photos up;
-- remaining paper = paper_capacity - PrintCount. 0 = unknown/not configured.
alter table public.liftpic_machine_configs
  add column if not exists paper_capacity integer not null default 0;

comment on column public.liftpic_machine_configs.paper_capacity is
  'Paper roll capacity (number of prints a full roll holds). 0 = unknown/not configured. Remaining paper = paper_capacity - PrintCount.';
