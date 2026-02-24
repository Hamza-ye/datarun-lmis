import { Routes } from '@angular/router';
import { DashboardLayout } from './layout/dashboard-layout/dashboard-layout';
import { StockBalances } from './features/ledger/components/stock-balances/stock-balances';
import { TransactionHistory } from './features/ledger/components/transaction-history/transaction-history';
import { NodeTree } from './features/kernel/components/node-tree/node-tree';
import { CommodityDictionary } from './features/kernel/components/commodity-dictionary/commodity-dictionary';
import { InboxForm } from './features/adapter/components/inbox-form/inbox-form';
import { TopologyWizard } from './features/kernel/components/topology-wizard/topology-wizard';
import { LossResolutionWizard } from './features/ledger/components/loss-resolution-wizard/loss-resolution-wizard';

export const routes: Routes = [
    {
        path: '',
        component: DashboardLayout,
        children: [
            { path: '', redirectTo: 'ledger/balances', pathMatch: 'full' },
            { path: 'ledger/balances', component: StockBalances },
            { path: 'ledger/history', component: TransactionHistory },
            { path: 'kernel/nodes', component: NodeTree },
            { path: 'kernel/commodities', component: CommodityDictionary },
            { path: 'adapter/inbox', component: InboxForm },
            { path: 'kernel/topology', component: TopologyWizard },
            { path: 'ledger/loss-resolution', component: LossResolutionWizard }
        ]
    },
    { path: '**', redirectTo: '' }
];
