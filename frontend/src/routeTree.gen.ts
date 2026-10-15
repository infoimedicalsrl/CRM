/* eslint-disable */
// @ts-nocheck
// Local route tree for Peppol Sales Analytics.
import { Route as rootRouteImport } from './routes/__root'
import { Route as IndexRouteImport } from './routes/index'
import { Route as OrdersRouteImport } from './routes/orders/index'
import { Route as OrderDetailRouteImport } from './routes/orders/$id'
import { Route as DDTsRouteImport } from './routes/ddts/index'
import { Route as DDTDetailRouteImport } from './routes/ddts/$id'
import { Route as ProductsRouteImport } from './routes/products/index'
import { Route as ProductDetailRouteImport } from './routes/products/$id'
import { Route as CustomersRouteImport } from './routes/customers/index'
import { Route as CustomerDetailRouteImport } from './routes/customers/$id'
import { Route as AnalyticsRouteImport } from './routes/analytics'
import { Route as ImportsRouteImport } from './routes/imports'
import { Route as SettingsRouteImport } from './routes/settings'
import { Route as BankRouteImport } from './routes/bank'
import { Route as SalesInvoicesRouteImport } from './routes/sales-invoices'
import { Route as PurchaseInvoicesRouteImport } from './routes/purchase-invoices'
import { Route as PurchaseInvoiceDetailRouteImport } from './routes/purchase-invoices/$id'
import { Route as SalesInvoiceDetailRouteImport } from './routes/sales-invoices/$id'
import { Route as CustomerStatementsRouteImport } from './routes/customer-statements'

const IndexRoute = IndexRouteImport.update({ id: '/', path: '/', getParentRoute: () => rootRouteImport } as any)
const OrdersRoute = OrdersRouteImport.update({ id: '/orders', path: '/orders', getParentRoute: () => rootRouteImport } as any)
const OrderDetailRoute = OrderDetailRouteImport.update({ id: '/orders/$id', path: '/orders/$id', getParentRoute: () => rootRouteImport } as any)
const DDTsRoute = DDTsRouteImport.update({ id: '/ddts/', path: '/ddts', getParentRoute: () => rootRouteImport } as any)
const DDTDetailRoute = DDTDetailRouteImport.update({ id: '/ddts/$id', path: '/ddts/$id', getParentRoute: () => rootRouteImport } as any)
const ProductsRoute = ProductsRouteImport.update({ id: '/products', path: '/products', getParentRoute: () => rootRouteImport } as any)
const ProductDetailRoute = ProductDetailRouteImport.update({ id: '/products/$id', path: '/products/$id', getParentRoute: () => rootRouteImport } as any)
const CustomersRoute = CustomersRouteImport.update({ id: '/customers', path: '/customers', getParentRoute: () => rootRouteImport } as any)
const CustomerDetailRoute = CustomerDetailRouteImport.update({ id: '/customers/$id', path: '/customers/$id', getParentRoute: () => rootRouteImport } as any)
const AnalyticsRoute = AnalyticsRouteImport.update({ id: '/analytics', path: '/analytics', getParentRoute: () => rootRouteImport } as any)
const ImportsRoute = ImportsRouteImport.update({ id: '/imports', path: '/imports', getParentRoute: () => rootRouteImport } as any)
const SettingsRoute = SettingsRouteImport.update({ id: '/settings', path: '/settings', getParentRoute: () => rootRouteImport } as any)
const BankRoute = BankRouteImport.update({ id: '/bank', path: '/bank', getParentRoute: () => rootRouteImport } as any)
const SalesInvoicesRoute = SalesInvoicesRouteImport.update({ id: '/sales-invoices', path: '/sales-invoices', getParentRoute: () => rootRouteImport } as any)
const PurchaseInvoicesRoute = PurchaseInvoicesRouteImport.update({ id: '/purchase-invoices', path: '/purchase-invoices', getParentRoute: () => rootRouteImport } as any)
const PurchaseInvoiceDetailRoute = PurchaseInvoiceDetailRouteImport.update({ id: '/purchase-invoices/$id', path: '/purchase-invoices/$id', getParentRoute: () => rootRouteImport } as any)
const SalesInvoiceDetailRoute = SalesInvoiceDetailRouteImport.update({ id: '/sales-invoices/$id', path: '/sales-invoices/$id', getParentRoute: () => rootRouteImport } as any)
const CustomerStatementsRoute = CustomerStatementsRouteImport.update({ id: '/customer-statements', path: '/customer-statements', getParentRoute: () => rootRouteImport } as any)

const rootRouteChildren = {
  IndexRoute,
  OrdersRoute,
  OrderDetailRoute,
  DDTsRoute,
  DDTDetailRoute,
  ProductsRoute,
  ProductDetailRoute,
  CustomersRoute,
  CustomerDetailRoute,
  AnalyticsRoute,
  ImportsRoute,
  SettingsRoute,
  BankRoute,
  SalesInvoicesRoute,
  PurchaseInvoicesRoute,
  PurchaseInvoiceDetailRoute,
  SalesInvoiceDetailRoute,
  CustomerStatementsRoute,
}

export const routeTree = rootRouteImport._addFileChildren(rootRouteChildren as any)

