/** UI strings (Spanish). Metric descriptions from the API are English; these labels take precedence. */

export const CATEGORY_LABELS: Record<string, string> = {
  economy: "Economía",
  size: "Tamaño y poder",
  military: "Militar",
  state: "Estado",
};

export const METRIC_LABELS: Record<string, string> = {
  gold: "Tesoro (oro)",
  monthly_income: "Ingresos del mes",
  tax_income: "Impuestos del mes",
  trade_value: "Valor comercial mensual",
  trade_balance: "Ingresos comerciales netos",
  inflation: "Inflación",
  maintenance: "Gasto mensual",
  total_produced: "Bienes producidos",
  population: "Población (en miles)",
  locations: "Localizaciones",
  provinces: "Provincias",
  core_locations: "Localizaciones núcleo",
  score_place: "Puesto en puntuación",
  score_adm: "Puntuación ADM",
  score_dip: "Puntuación DIP",
  score_mil: "Puntuación MIL",
  great_power_rank: "Rango de gran potencia",
  manpower: "Soldadesca (miles)",
  max_manpower: "Sold. máx. (miles)",
  sailors: "Marineros (miles)",
  max_sailors: "Marin. máx. (miles)",
  army_tradition: "Tradición del ejército",
  navy_tradition: "Tradición naval",
  armies: "Ejércitos",
  navies: "Flotas",
  regiments: "Regimientos",
  army_strength: "Fuerza del ejército",
  ships: "Barcos",
  expected_army_size: "Tamaño de ejército esperado",
  active_wars: "Guerras activas",
  stability: "Estabilidad",
  prestige: "Prestigio",
  war_exhaustion: "Cansancio bélico",
  advances: "Avances investigados",
  institutions: "Instituciones",
  political_influence: "Influencia política",
  // history metrics
  tax_base: "Base impositiva",
  economical_base: "Base económica",
};

export const metricLabel = (name: string, fallback?: string) => METRIC_LABELS[name] ?? fallback ?? name;
export const categoryLabel = (name: string) => CATEGORY_LABELS[name] ?? name;

export const STATUS_LABELS: Record<string, string> = {
  pending: "En cola",
  processing: "Procesando",
  done: "Procesado",
  error: "Error",
  duplicate: "Duplicada",
};

export const STATUS_LABELS_PLURAL: Record<string, string> = {
  pending: "en cola",
  processing: "procesando",
  done: "procesados",
  error: "con error",
  duplicate: "duplicados",
};

export const THEME_LABELS = { dark: "Modo oscuro", light: "Modo claro" };
