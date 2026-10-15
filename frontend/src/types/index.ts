export interface HealthStatus { status: string; }

export interface Customer {
  id: number;
  name: string;
  vat_number?: string | null;
  peppol_endpoint?: string | null;
  orders_count?: number;
  products_count?: number;
  total_quantity?: number;
  net_revenue?: number;
  gross_revenue?: number;
}

export interface Product {
  id: number;
  supplier_product_code: string;
  description?: string | null;
  quantity_ordered?: number;
  unit?: string | null;
  orders_count?: number;
  customers_count?: number;
  net_revenue?: number;
  vat_amount?: number;
  gross_revenue?: number;
  zero_value_quantity?: number;
}

export interface OrderLine {
  id?: number;
  line_number?: string | null;
  product_id?: number;
  supplier_product_code: string;
  description?: string | null;
  quantity?: number;
  unit?: string | null;
  unit_price?: number;
  line_net?: number;
  vat_category?: string | null;
  vat_rate?: number;
  vat_amount?: number;
  line_total?: number;
  is_zero_value?: boolean;
}

export interface Order {
  id: number;
  order_number: string;
  order_date?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  customer_vat?: string | null;
  customer?: Customer;
  currency?: string | null;
  net_amount?: number;
  vat_amount?: number;
  total_amount?: number;
  source_file?: string | null;
  lines?: OrderLine[];
  delivery?: DeliverySummary;
}

export interface TimeSeriesPoint { period: string; net?: number; vat?: number; total?: number; }
export interface QuantitySeriesPoint { period: string; [unit: string]: number | string; }

export interface DashboardSummary {
  net_revenue: number;
  gross_revenue: number;
  vat_amount: number;
  orders_count: number;
  customers_count: number;
  products_count: number;
  zero_value_quantity: number;
  revenue_series: TimeSeriesPoint[];
  quantity_series: QuantitySeriesPoint[];
  top_products: Product[];
  top_products_by_quantity: Product[];
  top_customers: Customer[];
  top_customers_by_orders: Customer[];
}

export interface ImportJob {
  id: number;
  file_name: string;
  created_at?: string | null;
  completed_at?: string | null;
  status: string;
  order_id?: number | null;
  order_number?: string | null;
  message?: string | null;
}

export interface ImportsResponse { items: ImportJob[]; total: number; success: number; errors: number; }
export interface GlobalFilterState { from?: string; to?: string; customerId?: string; productCode?: string; }

export interface ProductCustomerRow {
  customer_id: number;
  customer: string;
  product_id: number;
  supplier_product_code: string;
  description?: string | null;
  unit_code?: string | null;
  quantity: number;
  net: number;
}

export interface ZeroValueLine {
  id: number;
  product_id: number;
  supplier_product_code: string;
  description?: string | null;
  customer_id: number;
  customer_name?: string | null;
  order_id: number;
  order_number: string;
  order_date?: string | null;
  quantity?: number;
  unit?: string | null;
}

export interface DeliverySummaryLine {
  order_line_id: number;
  product_id: number;
  supplier_product_code: string;
  description?: string | null;
  unit_code?: string | null;
  ordered_quantity: number;
  delivered_quantity: number;
  ddt_delivered_quantity?: number;
  manual_delivered_quantity?: number | null;
  residual_quantity: number;
  over_quantity: number;
  status: string;
}
export interface DeliverySummary {
  status: string;
  ordered_quantity: number;
  delivered_quantity: number;
  residual_quantity: number;
  over_quantity?: number;
  lines: DeliverySummaryLine[];
  ddts: Array<{id:number;number:string;date?:string|null;quantity:number;status:string}>;
}
export interface DDTListItem {
  id:number; ddt_number:string; ddt_date?:string|null; customer_id?:number|null; customer_name?:string|null;
  order_id?:number|null; order_number?:string|null; order_reference?:string|null; status:string; source_filename:string; line_count:number; quantity:number;
}
export interface DDTLine {
  id:number; supplier_product_code:string; description?:string|null; quantity:number; unit_code?:string|null;
  lot_number?:string|null; expiry_date?:string|null; is_gift:boolean; is_unordered:boolean; product_id?:number|null;
  order_line_id?:number|null; order_line_quantity?:number|null;
}
export interface DDTDetail {
  id:number; ddt_number:string; ddt_date?:string|null; customer?:Customer|null; order_id?:number|null; order_number?:string|null;
  order_reference?:string|null; status:string; source_filename:string; lines:DDTLine[];
}
