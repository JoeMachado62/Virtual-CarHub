"""Tests for the NLP vehicle query parser (fallback regex path)."""

from app.services.nlp_query_service import ParsedVehicleQuery, _fallback_parse


class TestFallbackParse:
    def test_basic_make_model_year(self):
        result = _fallback_parse("2021 BMW X5")
        assert result.make == "Bmw"
        assert result.model == "X5"
        assert result.min_year == 2021
        assert result.max_year == 2021
        assert result.parsed is True
        assert result.parse_method == "fallback"

    def test_mileage_under(self):
        result = _fallback_parse("BMW X5 with under 40k miles")
        assert result.make == "Bmw"
        assert result.model == "X5"
        assert result.max_miles == 40000

    def test_mileage_over(self):
        result = _fallback_parse("Toyota Camry over 50000 miles")
        assert result.make == "Toyota"
        assert result.model == "Camry"
        assert result.min_miles == 50000

    def test_price_under(self):
        result = _fallback_parse("Ford F-150 under $30k")
        assert result.make == "Ford"
        assert result.max_price == 30000

    def test_price_around(self):
        result = _fallback_parse("Honda Civic around $25000")
        assert result.make == "Honda"
        assert result.model == "Civic"
        assert result.min_price is not None
        assert result.max_price is not None
        assert result.min_price < 25000 < result.max_price

    def test_year_range(self):
        result = _fallback_parse("Toyota between 2019 and 2022")
        assert result.min_year == 2019
        assert result.max_year == 2022

    def test_body_type_suv(self):
        result = _fallback_parse("I want an SUV under $40k")
        assert result.body_type == "suv"
        assert result.max_price == 40000

    def test_body_type_truck(self):
        result = _fallback_parse("Looking for a pickup truck")
        assert result.body_type == "truck"

    def test_drivetrain(self):
        result = _fallback_parse("BMW X5 AWD")
        assert result.drivetrain == "AWD"

    def test_fuel_type_electric(self):
        result = _fallback_parse("Tesla electric sedan")
        assert result.make == "Tesla"
        assert result.fuel_type == "electric"

    def test_fuel_type_hybrid(self):
        result = _fallback_parse("Toyota hybrid SUV")
        assert result.make == "Toyota"
        assert result.fuel_type == "hybrid"
        assert result.body_type == "suv"

    def test_chevy_alias(self):
        result = _fallback_parse("Chevy Silverado 2023")
        assert result.make == "Chevrolet"
        assert result.model == "Silverado"
        assert result.min_year == 2023

    def test_mercedes_alias(self):
        result = _fallback_parse("Mercedes GLE 2022")
        assert result.make == "Mercedes-Benz"
        assert result.model == "GLE"

    def test_empty_query(self):
        result = _fallback_parse("")
        assert result.parsed is True
        assert result.make is None
        assert result.model is None

    def test_no_vehicle_info(self):
        result = _fallback_parse("I want something nice")
        assert result.make is None
        assert result.model is None
        assert result.parsed is True

    def test_full_natural_language(self):
        result = _fallback_parse("I want a 2021 BMW X5 with under 40k miles")
        assert result.make == "Bmw"
        assert result.model == "X5"
        assert result.min_year == 2021
        assert result.max_year == 2021
        assert result.max_miles == 40000

    def test_complex_query(self):
        result = _fallback_parse("2022 Tesla Model 3 electric AWD under $45000 with less than 20000 miles")
        assert result.make == "Tesla"
        assert result.min_year == 2022
        assert result.max_year == 2022
        assert result.fuel_type == "electric"
        assert result.drivetrain == "AWD"
        assert result.max_price == 45000
        assert result.max_miles == 20000


class TestParsedVehicleQueryModel:
    def test_defaults(self):
        q = ParsedVehicleQuery()
        assert q.parsed is False
        assert q.parse_method == "none"
        assert q.make is None
        assert q.raw_query == ""

    def test_model_dump_filters(self):
        q = ParsedVehicleQuery(make="BMW", model="X5", min_year=2021, parsed=True, parse_method="llm")
        dump = q.model_dump()
        assert dump["make"] == "BMW"
        assert dump["model"] == "X5"
        assert dump["min_year"] == 2021
        assert dump["trim"] is None
