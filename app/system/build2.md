
| Phase     | What you build                                                                                    | Backend needed                                               |
| --------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Now**   | Public `/build` page with load calculator, budget inputs, 4 smart slots, localStorage persistence | None — just serve the template                               |
| **Next**  | HTMX endpoints: `/build/recommend`, `/build/swap/{category}`, `/build/validate`                   | Pydantic models, basic product filtering by category + price |
| **Later** | Compatibility engine, appliance estimator defaults, checkout bundling                             | The heavy logic                                              |


# Current /build features (check is unbuilt)

| Feature                                    | Status                                                    |
| ------------------------------------------ | --------------------------------------------------------- |
| Public `/build` page                       | ✅                                                         |
| Appliance calculator with defaults         | ✅                                                         |
| Budget min/max inputs                      | ✅                                                         |
| 4 smart slots with select / clear / browse | ✅                                                         |
| Running total                              | ✅                                                         |
| localStorage persistence for anon users    | ✅                                                         |
| Red compatibility banner (UI ready)        | ✅ — just call `showCompatWarning(msg)` from HTMX callback |
| Add system to cart                         | ✅ — wired to `SystemBundle` model                         |
| Auth modal on Faves/Cart                   | ✅ (unchanged from before)                                 |


## What to wire up
1. /build/recommend — POST the appliance list + budget, return 4 recommended product IDs. The frontend can then selectProduct() each one.
2. /build/alternatives/{category} — Return HTML of .slot-alt-card items for a category, filtered by budget. HTMX swaps them into the scroll row.
3. /build/validate — POST current selections, return warnings. If any, call showCompatWarning().
4. /cart/system — Accept a SystemBundle, validate auth, store it. If anon, redirect to sign-in with ?next=/build&system_state={encoded_json}.
