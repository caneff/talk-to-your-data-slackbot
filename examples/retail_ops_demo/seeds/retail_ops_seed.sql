-- Synthetic Retail Operations demo data for DuckDB.
-- This file is intentionally demo-only; tests should keep using inline fixtures.

drop table if exists demo_inventory_snapshots;
drop table if exists demo_support_tickets;
drop table if exists demo_order_lines;
drop table if exists demo_orders;
drop table if exists demo_products;
drop table if exists demo_customers;
drop table if exists demo_stores;

create table demo_stores (
    store_id varchar,
    store_name varchar,
    store_region varchar,
    store_channel varchar,
    opened_date date
);

create table demo_customers (
    customer_id varchar,
    created_date date,
    customer_segment varchar,
    customer_region varchar,
    loyalty_tier varchar,
    acquisition_channel varchar
);

create table demo_products (
    product_id varchar,
    sku varchar,
    product_category varchar,
    product_subcategory varchar,
    brand varchar,
    standard_cost decimal(12, 2),
    list_price decimal(12, 2)
);

create table demo_orders (
    order_id varchar,
    order_date date,
    customer_id varchar,
    store_id varchar,
    order_channel varchar,
    fulfillment_status varchar,
    promo_code varchar,
    shipping_region varchar,
    store_region varchar,
    customer_segment varchar,
    gross_revenue decimal(12, 2),
    discount_amount decimal(12, 2),
    net_revenue decimal(12, 2)
);

create table demo_order_lines (
    line_id varchar,
    order_id varchar,
    product_id varchar,
    order_date date,
    product_category varchar,
    product_subcategory varchar,
    brand varchar,
    quantity integer,
    unit_price decimal(12, 2),
    unit_cost decimal(12, 2),
    line_revenue decimal(12, 2),
    line_cost decimal(12, 2),
    returned_quantity integer
);

create table demo_support_tickets (
    ticket_id varchar,
    created_date date,
    customer_id varchar,
    order_id varchar,
    issue_category varchar,
    priority varchar,
    status varchar,
    first_response_minutes integer,
    resolution_hours decimal(12, 2)
);

create table demo_inventory_snapshots (
    snapshot_date date,
    store_id varchar,
    product_id varchar,
    product_category varchar,
    product_subcategory varchar,
    on_hand_units integer,
    stockout_days integer
);

insert into demo_stores
select
    'store-' || lpad(i::varchar, 3, '0') as store_id,
    case (i - 1) % 8
        when 0 then 'Boston Flagship'
        when 1 then 'Atlanta Market'
        when 2 then 'Chicago Loop'
        when 3 then 'Denver West'
        when 4 then 'Seattle Digital'
        when 5 then 'Phoenix Outlet'
        when 6 then 'New York Pop Up'
        else 'Dallas Fulfillment'
    end as store_name,
    case (i - 1) % 4
        when 0 then 'Northeast'
        when 1 then 'Southeast'
        when 2 then 'Midwest'
        else 'West'
    end as store_region,
    case (i - 1) % 3
        when 0 then 'Retail'
        when 1 then 'Digital'
        else 'Outlet'
    end as store_channel,
    date '2022-01-01' + (i * interval 45 day) as opened_date
from range(1, 9) as store_numbers(i);

insert into demo_customers
select
    'cust-' || lpad(i::varchar, 5, '0') as customer_id,
    date '2024-01-01' + (i % 760) * interval 1 day as created_date,
    case i % 4
        when 0 then 'Consumer'
        when 1 then 'Small Business'
        when 2 then 'Enterprise'
        else 'Education'
    end as customer_segment,
    case i % 5
        when 0 then 'Northeast'
        when 1 then 'Southeast'
        when 2 then 'Midwest'
        when 3 then 'West'
        else 'International'
    end as customer_region,
    case i % 4
        when 0 then 'Bronze'
        when 1 then 'Silver'
        when 2 then 'Gold'
        else 'Platinum'
    end as loyalty_tier,
    case i % 5
        when 0 then 'Paid Search'
        when 1 then 'Organic'
        when 2 then 'Referral'
        when 3 then 'Partner'
        else 'Email'
    end as acquisition_channel
from range(1, 361) as customer_numbers(i);

insert into demo_products
select
    'prod-' || lpad(i::varchar, 4, '0') as product_id,
    'SKU-' || lpad((70000 + i)::varchar, 5, '0') as sku,
    case i % 6
        when 0 then 'Apparel'
        when 1 then 'Home'
        when 2 then 'Electronics'
        when 3 then 'Outdoor'
        when 4 then 'Beauty'
        else 'Office'
    end as product_category,
    case i % 8
        when 0 then 'Core'
        when 1 then 'Premium'
        when 2 then 'Seasonal'
        when 3 then 'Clearance'
        when 4 then 'Accessories'
        when 5 then 'Bundles'
        when 6 then 'Services'
        else 'Essentials'
    end as product_subcategory,
    case i % 5
        when 0 then 'Northline'
        when 1 then 'BrightCo'
        when 2 then 'UrbanForge'
        when 3 then 'SummitWorks'
        else 'Everyday Lab'
    end as brand,
    round((8 + (i % 41) * 1.35)::decimal(12, 2), 2) as standard_cost,
    round((18 + (i % 47) * 2.40)::decimal(12, 2), 2) as list_price
from range(1, 97) as product_numbers(i);

insert into demo_orders
with order_base as (
    select
        i,
        'order-' || lpad(i::varchar, 6, '0') as order_id,
        date '2026-01-01' + (i % 151) * interval 1 day as order_date,
        'cust-' || lpad(((i * 17) % 360 + 1)::varchar, 5, '0') as customer_id,
        'store-' || lpad(((i * 5) % 8 + 1)::varchar, 3, '0') as store_id,
        case i % 4
            when 0 then 'Store'
            when 1 then 'Web'
            when 2 then 'Mobile'
            else 'Marketplace'
        end as order_channel,
        case i % 10
            when 0 then 'Cancelled'
            when 1 then 'Returned'
            when 2 then 'Partially Shipped'
            else 'Shipped'
        end as fulfillment_status,
        case i % 6
            when 0 then 'WELCOME10'
            when 1 then 'SPRING20'
            when 2 then 'LOYALTY15'
            else null
        end as promo_code,
        case i % 5
            when 0 then 'Northeast'
            when 1 then 'Southeast'
            when 2 then 'Midwest'
            when 3 then 'West'
            else 'International'
        end as shipping_region
    from range(1, 1801) as order_numbers(i)
)
select
    order_id,
    order_date,
    customer_id,
    store_id,
    order_channel,
    fulfillment_status,
    promo_code,
    shipping_region,
    case (i * 5) % 8
        when 0 then 'Southeast'
        when 1 then 'Midwest'
        when 2 then 'West'
        when 3 then 'Northeast'
        when 4 then 'Southeast'
        when 5 then 'Midwest'
        when 6 then 'West'
        else 'Northeast'
    end as store_region,
    case ((i * 17) % 360 + 1) % 4
        when 0 then 'Consumer'
        when 1 then 'Small Business'
        when 2 then 'Enterprise'
        else 'Education'
    end as customer_segment,
    round((45 + (i % 220) * 3.85)::decimal(12, 2), 2) as gross_revenue,
    round(
        case when promo_code is null then 0 else 5 + (i % 35) * 1.25 end,
        2
    )::decimal(12, 2) as discount_amount,
    round(
        (45 + (i % 220) * 3.85)
        - case when promo_code is null then 0 else 5 + (i % 35) * 1.25 end,
        2
    )::decimal(12, 2) as net_revenue
from order_base;

insert into demo_order_lines
with line_base as (
    select
        i,
        order_line_number,
        'order-' || lpad(i::varchar, 6, '0') as order_id,
        'prod-' || lpad(((i * 13 + order_line_number * 7) % 96 + 1)::varchar, 4, '0') as product_id,
        1 + ((i + order_line_number) % 4) as quantity
    from range(1, 1801) as order_numbers(i)
    cross join range(1, 4) as line_numbers(order_line_number)
)
select
    order_id || '-line-' || order_line_number::varchar as line_id,
    order_id,
    product_id,
    date '2026-01-01' + (i % 151) * interval 1 day as order_date,
    case ((i * 13 + order_line_number * 7) % 96 + 1) % 6
        when 0 then 'Apparel'
        when 1 then 'Home'
        when 2 then 'Electronics'
        when 3 then 'Outdoor'
        when 4 then 'Beauty'
        else 'Office'
    end as product_category,
    case ((i * 13 + order_line_number * 7) % 96 + 1) % 8
        when 0 then 'Core'
        when 1 then 'Premium'
        when 2 then 'Seasonal'
        when 3 then 'Clearance'
        when 4 then 'Accessories'
        when 5 then 'Bundles'
        when 6 then 'Services'
        else 'Essentials'
    end as product_subcategory,
    case ((i * 13 + order_line_number * 7) % 96 + 1) % 5
        when 0 then 'Northline'
        when 1 then 'BrightCo'
        when 2 then 'UrbanForge'
        when 3 then 'SummitWorks'
        else 'Everyday Lab'
    end as brand,
    quantity,
    round((16 + ((i + order_line_number) % 54) * 2.10)::decimal(12, 2), 2) as unit_price,
    round((7 + ((i + order_line_number) % 39) * 1.15)::decimal(12, 2), 2) as unit_cost,
    round((quantity * (16 + ((i + order_line_number) % 54) * 2.10))::decimal(12, 2), 2) as line_revenue,
    round((quantity * (7 + ((i + order_line_number) % 39) * 1.15))::decimal(12, 2), 2) as line_cost,
    case when (i + order_line_number) % 17 = 0 then 1 else 0 end as returned_quantity
from line_base;

insert into demo_support_tickets
select
    'ticket-' || lpad(i::varchar, 5, '0') as ticket_id,
    date '2026-01-01' + (i % 151) * interval 1 day as created_date,
    'cust-' || lpad(((i * 19) % 360 + 1)::varchar, 5, '0') as customer_id,
    'order-' || lpad(((i * 23) % 1800 + 1)::varchar, 6, '0') as order_id,
    case i % 6
        when 0 then 'Delivery'
        when 1 then 'Return'
        when 2 then 'Billing'
        when 3 then 'Product Question'
        when 4 then 'Damaged Item'
        else 'Account'
    end as issue_category,
    case i % 4
        when 0 then 'Low'
        when 1 then 'Medium'
        when 2 then 'High'
        else 'Urgent'
    end as priority,
    case i % 5
        when 0 then 'Open'
        when 1 then 'Waiting on Customer'
        else 'Resolved'
    end as status,
    5 + (i % 180) as first_response_minutes,
    round((1 + (i % 96) * 0.75)::decimal(12, 2), 2) as resolution_hours
from range(1, 521) as ticket_numbers(i);

insert into demo_inventory_snapshots
select
    date '2026-01-31' + month_number * interval 1 month as snapshot_date,
    'store-' || lpad(store_number::varchar, 3, '0') as store_id,
    'prod-' || lpad(product_number::varchar, 4, '0') as product_id,
    case product_number % 6
        when 0 then 'Apparel'
        when 1 then 'Home'
        when 2 then 'Electronics'
        when 3 then 'Outdoor'
        when 4 then 'Beauty'
        else 'Office'
    end as product_category,
    case product_number % 8
        when 0 then 'Core'
        when 1 then 'Premium'
        when 2 then 'Seasonal'
        when 3 then 'Clearance'
        when 4 then 'Accessories'
        when 5 then 'Bundles'
        when 6 then 'Services'
        else 'Essentials'
    end as product_subcategory,
    12 + ((store_number * product_number + month_number) % 140) as on_hand_units,
    case
        when (store_number * product_number + month_number) % 11 = 0 then 4
        when (store_number * product_number + month_number) % 7 = 0 then 2
        else 0
    end as stockout_days
from range(0, 8) as month_numbers(month_number)
cross join range(1, 9) as store_numbers(store_number)
cross join range(1, 97) as product_numbers(product_number);
