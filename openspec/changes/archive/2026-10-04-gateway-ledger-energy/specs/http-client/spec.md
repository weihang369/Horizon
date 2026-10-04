# Spec Delta

## ADDED Requirements

### Requirement: Settings and energy over HTTP
The `HttpClient` SHALL implement the following methods against the backend:
- `settings.update` → `PATCH /settings`;
- `settings.setKey` → `PUT /settings/key`;
- `settings.testConnection` → `POST /settings/test-connection`;
- `settings.testModel` → `POST /settings/test-model`;
- `characters.topUpEnergy` → `POST /characters/{id}/energy/top-up`;
- `characters.setEnergyMax` → `PUT /characters/{id}/energy/max`.

None of these methods SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`.

#### Scenario: Top-up over HTTP
- **WHEN** `characters.topUpEnergy("chr_seedHana", 500)` is called with a key set
- **THEN** one `POST /characters/chr_seedHana/energy/top-up` is sent with an `Idempotency-Key`, and the returned `Energy` is shown

#### Scenario: Top-up refused
- **WHEN** a top-up is refused by the backend with 402 `daily_budget_exceeded`
- **THEN** the method rejects with a `HorizonError` whose `code` is `daily_budget_exceeded`

#### Scenario: Not pending any more
- **WHEN** `settings.setKey` is called on the `HttpClient`
- **THEN** a `PUT /settings/key` request is sent, and the method does not reject with `details.availableIn: "M2"`
