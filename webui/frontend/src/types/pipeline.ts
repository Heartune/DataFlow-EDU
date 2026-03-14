export interface TaxonomyItem {
  name?: string;
  subcategories?: string[];
}

export interface Stage1Pair {
  pair_index?: number;
  page_info?: string;
  subcategories?: string[];
  [key: string]: unknown;
}

export interface Stage1Data {
  total_pages?: number;
  total_pairs?: number;
  pairs?: Stage1Pair[];
  [key: string]: unknown;
}

export interface Question {
  question?: string;
  answer?: string;
  type?: string;
  subcategory?: string;
  category?: string;
  ability_level?: string;
  ability_main?: string;
  difficulty?: string;
  source_page?: string;
  [key: string]: unknown;
}

export interface Stage2Data {
  questions?: Question[];
  [key: string]: unknown;
}

export interface Stage3Data extends Stage2Data {}

export interface EduConfig {
  taxonomy?: TaxonomyItem[];
  [key: string]: unknown;
}

export interface LoadedData {
  config: EduConfig;
  stage1: Stage1Data;
  stage2: Stage2Data;
  stage3: Stage3Data;
}
