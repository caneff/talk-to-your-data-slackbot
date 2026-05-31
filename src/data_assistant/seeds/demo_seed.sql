-- Demo spine rows for the local Slack-like demo.
-- Orders rows drive the revenue-by-region output, and customers rows drive the
-- customer-count-by-region output.
insert into orders (order_date, region, revenue) values
    ('2026-01-03', 'North', 1200.00),
    ('2026-01-10', 'North',  300.00),
    ('2026-01-12', 'South',  800.00),
    ('2026-01-20',  NULL,    500.00),
    ('2026-01-28', 'West',   NULL);

insert into customers (created_date, customer_id, customer_region) values
    ('2026-01-03', 'cust-001', 'North'),
    ('2026-01-08', 'cust-002', 'South'),
    ('2026-01-15', 'cust-003', 'North'),
    ('2026-01-22', 'cust-004', 'East'),
    ('2026-01-28', 'cust-005',  NULL),
    ('2026-02-01', 'cust-006', 'West');
