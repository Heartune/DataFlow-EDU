export interface TaxonomyItem {
  name: string;
  subcategories: string[];
}

export interface QuestionType {
  name: string;
  weight: number;
}

export interface AbilityLevelItem {
  name: string;
  weight: number;
  description: string;
  sublevels: string[];
}

export interface EduConfig {
  taxonomy: TaxonomyItem[];
  question_types: QuestionType[];
  ability_levels: AbilityLevelItem[];
  operators: Record<string, Record<string, unknown>>;
}
