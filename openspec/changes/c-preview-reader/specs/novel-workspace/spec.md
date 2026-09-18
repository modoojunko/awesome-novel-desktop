## MODIFIED Requirements

### Requirement: PRO container (N14)

- The system SHALL provide `components/novel/ProContainer.tsx` that renders its children only when the user is on a paid tier.
- `ProContainer` SHALL use `useTier().isFree` to decide; when free, it SHALL render `null` and NOT render the subtree.
- The phase-driven UI — `OnboardingCard` and the `useNovelState` phase-status hook — SHALL be placed inside a ProContainer subtree so that free users render none of them and issue no phase-status request.
- The `GateBanner` phase-warning banner SHALL NOT be rendered anywhere in the novel workspace for any tier.
- The three navigation labels (编辑设定 / 编辑正文 / 预览) SHALL render for both tiers outside the ProContainer subtree.
- Hooks inside the ProContainer subtree SHALL NOT be called at the top level of NovelWorkspace (no conditional hook calls); they live inside a child component that only mounts for paid users.

#### Scenario: Free tier renders no phase UI
- Given a free-tier user viewing the workspace
- When the workspace renders
- Then no OnboardingCard or `GET .../workflow/phase-status` request is issued

#### Scenario: Paid tier renders phase UI
- Given a paid-tier user viewing the workspace
- When the workspace renders
- Then the OnboardingCard phase surface is present and a `GET .../workflow/phase-status` request is issued

#### Scenario: No gate banner on any tier
- Given a paid-tier user viewing the workspace with unconfirmed settings
- When the workspace renders
- Then no「以下阶段尚未就绪」gate banner is present in the DOM
