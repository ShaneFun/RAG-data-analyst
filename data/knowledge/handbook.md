# Larkspur Market Data Handbook

The analytics team's guide to the shop database: what the data means, the business rules
behind each metric, and the mistakes people make most often. Read the relevant section before
building a report.

## About Larkspur Market

### What the shop sells
Larkspur Market is an online shop selling 120 products across six categories: Electronics,
Home, Fashion, Beauty, Sports and Grocery. Each category has 20 products, named by category and
number, for example "Electronics Item 01" or "Grocery Item 17". Price ranges differ a lot by
category: Electronics items cost roughly $50 to $800, while Grocery items cost $2 to $40. Because
of this, revenue comparisons between categories are dominated by Electronics, and unit
comparisons are a better measure of popularity.

### Suppliers
Products come from eight suppliers: Brightline Goods, Copperleaf Trading, Harbor & Pine Co,
Meridian Wholesale, Oakridge Partners, Silverstream Supply, Tidewater Imports and Willow Lane
Makers. Each supplier provides exactly 15 products, spread across several categories, so a
supplier is not the same thing as a category. The supplier is stored as text on the products
table; there is no separate suppliers table. To analyse anything by supplier, join order_items
to products and group by products.supplier.

### Time range covered
The database contains two full years of orders, from 1 January 2024 to 31 December 2025. There
are no orders before or after that range. Year-over-year comparisons are possible for every
month. All customers signed up during 2023, before the first order, so every customer in the
data is an existing customer when the order history begins.

## Orders and order lines

### Order status
Every order has a status of either completed or cancelled. A cancelled order was never shipped
or paid for. Cancelled orders still have order lines in order_items, which record what the
customer tried to buy, but they must be excluded from sales, revenue, units sold and average
order value. Use cancelled orders only when the question is about cancellations themselves.
Roughly one order in twenty is cancelled.

### Order date and region
order_date is the date the customer checked out. It is a plain date with no time of day and no
time zone. The region on an order is the customer's home region at checkout, so orders.region
and customers_safe.region always agree. For regional reports, use orders.region directly; it
avoids an extra join.

### Order lines
An order contains one to four order lines. Each line is one product with a quantity of one to
three units. The unit_price on order_items is the price the customer actually paid per unit at
the time of the order. Always calculate money from order_items.unit_price, not from
products.unit_price, which is only the current list price shown in the catalogue. Line revenue
is quantity multiplied by unit_price.

## Revenue reporting rules

### Gross revenue
Gross revenue, also called sales or revenue, is the sum of quantity times unit_price over order
lines whose order is completed. It is the default meaning of "revenue" in every report unless
the question explicitly says net revenue.

### Net revenue
Net revenue is gross revenue minus the money returned through refunds. Subtract the refunds
that belong to the same order lines, joining refunds on refunds.order_item_id = order_items.id
with a LEFT JOIN so that lines without refunds are kept. Net revenue for a period is based on
the order date, not the refund date, so that a period's figure does not change meaning
depending on when customers return items.

### Average order value
Average order value (AOV) is gross revenue divided by the number of distinct completed orders.
Count orders with COUNT(DISTINCT orders.id), never with COUNT(*) after joining order lines,
because the join repeats each order once per line and would make AOV too small.

### Currency and rounding
All amounts are in US dollars. Round money to two decimal places only in the final SELECT, not
in intermediate steps, to avoid rounding errors adding up. Rates and shares are reported as
fractions between 0 and 1 in SQL and converted to percentages in the written answer.

## Refunds

### Refund policy
Customers may return an item within 30 days of the order. Refunds are made per order line: the
whole line is refunded or none of it, and a line can be refunded at most once. The refund amount
is the full amount paid for that line, quantity times unit_price. Only completed orders can be
refunded, since cancelled orders were never paid.

### Refund reasons
Every refund records one of five reasons. "damaged" means the item arrived broken.
"wrong item" means the warehouse shipped a different product. "not as described" means the
product did not match its listing. "changed mind" means the customer no longer wanted it.
"late delivery" means the parcel arrived after the promised date. Damaged, wrong item and late
delivery point to fulfilment problems; not as described points to product or listing quality;
changed mind is normal customer behaviour.

### Refund dates and refund rate
refund_date is between 3 and 30 days after the order date. When reporting refund rates, group
by the order date of the refunded line, so each refund is compared with the orders it came
from. When reporting cash paid out in a month, group by refund_date instead. The refund rate is
the number of refunded order lines divided by the number of order lines in completed orders.

## Customers and privacy

### Personal data
The customers table holds personal data: full names and email addresses. Analysts and the AI
analyst never read that table. They use the customers_safe view, which contains only id,
region, signup_date and signup_channel. Requests for names, emails or lists of identifiable
customers must be declined, even for internal use.

### Active and new customers
A customer is active in a period if they placed at least one completed order in it: count
distinct orders.customer_id. Because every customer signed up in 2023, signup_date cannot be
used to find new customers in 2024 or 2025. A customer's first purchase is their earliest
completed order date, found with MIN(order_date) grouped by customer_id.

### Signup channel versus order channel
signup_channel on customers_safe records how the customer created their account, web or app.
channel on orders records where each individual order was placed. A customer who signed up on
the web may later order through the app, so the two must not be confused. Questions about
"app customers" usually mean signup_channel; questions about "app orders" or "app sales" mean
orders.channel.

## Calendar and periods

### Months, quarters and years
The reporting calendar is the normal calendar year: Q1 is January to March, Q2 April to June,
Q3 July to September and Q4 October to December. Group by month with
DATE_TRUNC('month', order_date) and by quarter with DATE_TRUNC('quarter', order_date). Filter
a year with order_date >= '2025-01-01' AND order_date < '2026-01-01' rather than with
EXTRACT(YEAR ...), so the index on order_date can be used.

### Comparing periods
To explain a change between two periods, compare the same metric for both periods and break it
down by one dimension at a time: region, category, supplier, channel or product. The dimension
whose difference accounts for most of the total change is usually the explanation. Compare
units as well as revenue, because a revenue change can come from fewer orders, fewer items per
order, or a shift towards cheaper or more expensive products.

## Query tips and common mistakes

### Joins that double count
Joining orders to order_items produces one row per order line, and joining refunds adds no
extra rows because each line has at most one refund. Joining customers_safe to orders and then
to order_items repeats customer attributes on every line. Whenever a count is about orders or
customers rather than lines, use COUNT(DISTINCT ...).

### Performance
Queries time out after five seconds and return at most 200 rows. Aggregate in SQL with SUM,
COUNT and GROUP BY instead of fetching raw rows, filter on order_date where possible, and avoid
SELECT * on order_items, which has more than twenty thousand rows.
