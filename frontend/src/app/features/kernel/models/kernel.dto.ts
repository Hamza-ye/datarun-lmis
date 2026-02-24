export interface NodeRegistry {
    uid: string;
    code: string;
    name: string;
    node_type: string;
    parent_id?: string | null;
    valid_from: string; // YYYY-MM-DD
    valid_to?: string | null;
    meta_data?: any;
}

export interface CommodityRegistry {
    item_id: string;
    code: string;
    name: string;
    base_unit: string;
    status: 'ACTIVE' | 'DEPRECATED';
}

export interface NodeTopologyCorrection {
    new_parent_id: string;
    effective_date: string; // YYYY-MM-DD
}
