-- Demo spine rows for the local Slack-like demo (orders table).
-- These rows drive the demo's asserted output, including the deliberate NULLs
-- that exercise the data-quality caveat copy (missing region, missing revenue).
insert into orders (order_date, region, revenue) values
    ('2026-01-03', 'North', 1200.00),
    ('2026-01-10', 'North',  300.00),
    ('2026-01-12', 'South',  800.00),
    ('2026-01-20',  NULL,    500.00),
    ('2026-01-28', 'West',   NULL);
