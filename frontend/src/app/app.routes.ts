import { Routes } from '@angular/router';
import { DashboardLayout } from './layout/dashboard-layout/dashboard-layout';
import { StockBalances } from './features/ledger/components/stock-balances/stock-balances';
import { TransactionHistory } from './features/ledger/components/transaction-history/transaction-history';
import { NodeTree } from './features/kernel/components/node-tree/node-tree';
import { CommodityDictionary } from './features/kernel/components/commodity-dictionary/commodity-dictionary';
import { InboxForm } from './features/adapter/components/inbox-form/inbox-form';
import { TopologyWizard } from './features/kernel/components/topology-wizard/topology-wizard';
import { LossResolutionWizard } from './features/ledger/components/loss-resolution-wizard/loss-resolution-wizard';
import { DlqDashboard } from './features/adapter/components/dlq-dashboard/dlq-dashboard';
import { StagedInbox } from './features/ledger/components/staged-inbox/staged-inbox';
import { TransfersList } from './features/ledger/components/transfers-list/transfers-list';
import { ContractDashboard } from './features/adapter/components/contract-dashboard/contract-dashboard';
import { CrosswalkDashboard } from './features/adapter/components/crosswalk-dashboard/crosswalk-dashboard';

export const routes: Routes = [
    {
        path: '',
        component: DashboardLayout,
        children: [
            { path: '', redirectTo: 'ledger/balances', pathMatch: 'full' },
            { path: 'ledger/balances', component: StockBalances },
            { path: 'ledger/history', component: TransactionHistory },
            { path: 'ledger/staged-inbox', component: StagedInbox },
            { path: 'ledger/transfers', component: TransfersList },
            { path: 'kernel/nodes', component: NodeTree },
            { path: 'kernel/commodities', component: CommodityDictionary },
            { path: 'adapter/inbox', component: InboxForm },
            { path: 'adapter/admin/dlq', component: DlqDashboard },
            { path: 'adapter/admin/contracts', component: ContractDashboard },
            { path: 'adapter/admin/crosswalks', component: CrosswalkDashboard },
            { path: 'kernel/topology', component: TopologyWizard },
            { path: 'ledger/loss-resolution', component: LossResolutionWizard }
        ]
    },
    { path: '**', redirectTo: '' }
];
