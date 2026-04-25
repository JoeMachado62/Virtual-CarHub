/**
 * Canonical vehicle option lists shared between QuickMatchForm and
 * InventoryExplorer so that profile selections map 1-to-1 to search filters.
 *
 * Values are stored lowercase in bfv_json and matched case-insensitively
 * against Vehicle.body_type / Vehicle.make in the inventory search.
 */

/** Body types that appear in our inventory data. */
export const BODY_TYPE_OPTIONS = [
  "Sedan",
  "SUV",
  "Truck",
  "Coupe",
  "Convertible",
  "Hatchback",
  "Wagon",
  "Van",
  "Minivan",
  "Crossover",
  "Pickup",
];

/** Makes sourced from our taxonomy / NLP known-makes list. */
export const MAKE_OPTIONS = [
  "Acura",
  "Alfa Romeo",
  "Aston Martin",
  "Audi",
  "Bentley",
  "BMW",
  "Buick",
  "Cadillac",
  "Chevrolet",
  "Chrysler",
  "Dodge",
  "Ferrari",
  "Fiat",
  "Ford",
  "Genesis",
  "GMC",
  "Honda",
  "Hyundai",
  "Infiniti",
  "Jaguar",
  "Jeep",
  "Kia",
  "Lamborghini",
  "Land Rover",
  "Lexus",
  "Lincoln",
  "Lotus",
  "Lucid",
  "Maserati",
  "Mazda",
  "McLaren",
  "Mercedes-Benz",
  "Mini",
  "Mitsubishi",
  "Nissan",
  "Polestar",
  "Porsche",
  "Ram",
  "Rivian",
  "Rolls-Royce",
  "Subaru",
  "Suzuki",
  "Tesla",
  "Toyota",
  "Volkswagen",
  "Volvo",
];
