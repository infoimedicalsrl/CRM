import { apiGet, type QueryParams } from "./api";
import type { Customer, DashboardSummary, GlobalFilterState, HealthStatus, Product, QuantitySeriesPoint, TimeSeriesPoint } from "@/types";

export function filtersToParams(filters?: GlobalFilterState): QueryParams {
  return {
    date_from: filters?.from,
    date_to: filters?.to,
    customer_id: filters?.customerId,
    supplier_product_code: filters?.productCode,
  };
}

export function getHealth() {
  return apiGet<HealthStatus>("/api/health");
}

interface RawSummary {
  total_net: number;
  total_vat: number;
  total_gross: number;
  orders: number;
  customers: number;
  products: number;
  zero_value_quantity: number;
}
interface RawTrend { period: string; net: number; vat: number; gross: number; }
interface RawTopProduct { id: number; supplier_product_code: string; description?: string | null; unit_code?: string | null; quantity: number; net: number; }
interface RawTopCustomer { id: number; name: string; vat_number?: string | null; orders: number; net: number; }

export async function getDashboard(filters?: GlobalFilterState): Promise<DashboardSummary> {
  const params = filtersToParams(filters);
  const [summary, trend, quantity, topProducts, topProductsQuantity, topCustomers, topCustomersOrders] = await Promise.all([
    apiGet<RawSummary>("/api/dashboard", params),
    apiGet<RawTrend[]>("/api/analytics/revenue-trend", params),
    apiGet<QuantitySeriesPoint[]>("/api/analytics/quantity-trend", params),
    apiGet<RawTopProduct[]>("/api/analytics/top-products", { ...params, metric: "net", limit: 10 }),
    apiGet<RawTopProduct[]>("/api/analytics/top-products", { ...params, metric: "quantity", limit: 10 }),
    apiGet<RawTopCustomer[]>("/api/analytics/top-customers", { ...params, metric: "net", limit: 10 }),
    apiGet<RawTopCustomer[]>("/api/analytics/top-customers", { ...params, metric: "orders", limit: 10 }),
  ]);

  return {
    net_revenue: Number(summary.total_net ?? 0),
    vat_amount: Number(summary.total_vat ?? 0),
    gross_revenue: Number(summary.total_gross ?? 0),
    orders_count: summary.orders ?? 0,
    customers_count: summary.customers ?? 0,
    products_count: summary.products ?? 0,
    zero_value_quantity: Number(summary.zero_value_quantity ?? 0),
    revenue_series: trend.map<TimeSeriesPoint>((x) => ({ period: x.period, net: Number(x.net), vat: Number(x.vat), total: Number(x.gross) })),
    quantity_series: quantity,
    top_products: topProducts.map<Product>((x) => ({
      id: x.id,
      supplier_product_code: x.supplier_product_code,
      description: x.description,
      unit: x.unit_code,
      quantity_ordered: Number(x.quantity ?? 0),
      net_revenue: Number(x.net ?? 0),
    })),
    top_products_by_quantity: topProductsQuantity.map<Product>((x) => ({
      id: x.id,
      supplier_product_code: x.supplier_product_code,
      description: x.description,
      unit: x.unit_code,
      quantity_ordered: Number(x.quantity ?? 0),
      net_revenue: Number(x.net ?? 0),
    })),
    top_customers: topCustomers.map<Customer>((x) => ({
      id: x.id,
      name: x.name,
      vat_number: x.vat_number,
      orders_count: x.orders,
      net_revenue: Number(x.net ?? 0),
    })),
    top_customers_by_orders: topCustomersOrders.map<Customer>((x) => ({
      id: x.id,
      name: x.name,
      vat_number: x.vat_number,
      orders_count: x.orders,
      net_revenue: Number(x.net ?? 0),
    })),
  };
}

export async function getTopProducts(
  metric: "revenue" | "quantity",
  filters?: GlobalFilterState,
): Promise<Product[]> {
  const params = filtersToParams(filters);
  const rows = await apiGet<RawTopProduct[]>("/api/analytics/top-products", {
    ...params,
    metric: metric === "revenue" ? "net" : "quantity",
    limit: 10,
  });
  return rows.map<Product>((x) => ({
    id: x.id,
    supplier_product_code: x.supplier_product_code,
    description: x.description,
    unit: x.unit_code,
    quantity_ordered: Number(x.quantity ?? 0),
    net_revenue: Number(x.net ?? 0),
  }));
}

export interface PeriodComparison { current_period:{from:string;to:string}; previous_period:{from:string;to:string}; current:{net:number;gross:number;orders:number;customers:number}; previous:{net:number;gross:number;orders:number;customers:number}; change_percent:{net:number|null;gross:number|null;orders:number|null;customers:number|null}; }
export function getPeriodComparison(from:string,to:string){ return apiGet<PeriodComparison>("/api/analytics/period-comparison", {date_from:from,date_to:to}); }

export interface DeliveryDashboardSummary {open_orders:number;partial_orders:number;complete_orders:number;over_orders:number;residual_quantity:number;ddt_count:number;}
export function getDeliveryDashboard(){return apiGet<DeliveryDashboardSummary>("/api/dashboard/delivery-summary");}
