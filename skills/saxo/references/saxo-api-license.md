# Saxo Bank — 3rd Party Open API Application Development Non-Commercial License

> **Source:** This text was captured from the disclaimer/license shown during
> live app registration on the Saxo developer portal
> (https://www.developer.saxo/openapi/appmanagement#/connectlive), April 2026.
>
> **Availability:** This document is NOT publicly hosted at any stable URL.
> It is a private bilateral agreement distributed by Saxo Bank via email
> after a gated approval process. No linkable copy exists.
>
> **For personal-use apps** (direct retail clients building tools for their own
> account), the clickthrough disclaimer shown during portal registration is the
> operative agreement. The full 3rd-party licence process (evaluation form →
> openapisupport@saxobank.com → countersigned agreement) applies to 3rd parties
> building apps for others.

---

## DISCLAIMER

### General

I confirm that at no time is an AppSecret or a RefreshToken sent to a public
location, such as a browser or a downloadable application outside my premises.

> SPAs or downloadable platforms should use either the Implicit grant or PKCE

I confirm that I have performed the "monkey test".

> Pressing buttons in rapid random succession, should not cause your app to
> crash, hang or enter an infinite loop.

I confirm that my app does not generate excessive amounts of OpenAPI errors.

> If you get any 400 errors, please investigate if they are due to an
> application error.

I confirm that my app is not hitting the throttling limits in place.

> Please make sure you stay within the allocated throttling profile. You should
> not get a lot of 429 or 409 errors.

### Reading Data

I confirm that my app does not crash or hang if many positions or orders
are loaded.

I confirm that I do not assume client, account or instrument currencies.

> Even if your app is primarily handling a single currency, you should not
> assume that prices and balances are only in that currency.

I confirm that I correctly show data, especially prices and amounts.

> Especially, but not limited to, using the correct decimal separator (',' or
> '.') and correctly handling the number of decimals and tick sizes for
> instruments. Always check that what your application shows matches what is
> shown in Saxo Banks platforms.

I confirm that my app gracefully handles unexpected instruments, asset types
or positions.

> Even if your app doesn't support trading in specific instruments or asset
> types, these can often still be traded through Saxo's platforms. In most
> cases you cannot expect to only have a limited subset of instruments to deal
> with.

I confirm that my app correctly handles fractional amounts.

> Several asset types can be traded in fractional amounts, and even if your
> application doesn't support fractional orders, clients can still have
> fractional positions from trades done outside of your application, so make
> sure that your app can work with non-integer amounts.

### Trading

I confirm that I have tested all order types and order combinations that my
app supports.

> For example:
> - Create three way order (limit entry, stop loss, limit take profit).
> - Modify the above order.
> - Modify the limit entry order to market order (if market is open, if market
>   is open, the order should now get executed and become a position).
> - Delete related orders, or.
> - Modify related orders.

I confirm that my app prevents invalid orders as far as possible, and handles
rejected orders gracefully.

> Invalid orders include:
> - Wrong side of the market
> - Very, very large orders (out of margin)
> - Orders with negative amounts
> - Incorrectly formatted numbers
> - Placing multiple orders rapidly (should be throttled)

I confirm that if my app trades automatically, sensible safety measures are
in place to prevent unintended orders being placed.

> This could for example be:
> - System presents all proposed trades to you for final confirmation.
> - System stops if number of trades pr. time unit exceeds set limit.
> - You are informed if no/trades pr. time unit or size/trade exceeds set limits.
> - System is only running when you are logged in and can monitor behaviour.
> - You receive and review trade activity on a daily basis.

### Future Changes

I confirm that I have read and understood the interface versioning and
obsolescence policy.

> You can read the policy here: versioning and obsolescence policy. Important
> parts are:
> - We will often add more fields to a return contract.
> - We will often add more possible values to an enumeration type (i.e. a new
>   asset type, a new order type, a new account type etc). Your deserialisation
>   code must be able to handle this seamlessly.

---

## 3RD PARTY OPEN API APPLICATION DEVELOPMENT NON-COMMERCIAL LICENSE

This 3 Party Open API Application Development Non-commercial License
(hereafter "License") is an agreement between the Saxo Bank Group, Philip
Heymans Allé 15, DK-2900 Hellerup, Denmark (Company No: 15731249) (hereafter
"Saxo Bank") and you (hereafter "You" or "Your"), regarding Your usage of
Saxo Bank's Open API as set out below. By signing and returning this document
you acknowledge that You are legally bound by this License. Saxo Bank has
developed an Open API programming interface ("Open API") to permit its clients
to use their own internal proprietary software tools in managing and trading on
their accounts held with Saxo Bank. This license is only for individuals who
are developing software applications for trading on their own accounts held at
Saxo Bank. It is not intended for anybody developing third party applications
for general usage, or for any Saxo Bank introducing broker or Saxo Bank white
label client.

### 1. DEFINITIONS

1.1. "Access Token" will mean a token which must be provided by the App when
calling Open API. The token identifies an End User as well as the App.

1.2. "App" will mean the software and service provided by You which allows an
End User to interact with the Trading Platform via Open API.

1.3. "App Key" will mean a text string which uniquely identifies the App when
interacting with the Saxo Authentication System.

1.4. "App Secret" will mean a text string which must be kept secret by You and
which when presented together with the App Key authenticates the App towards
the Saxo Authentication System.

1.5. "End User" will mean any Saxo Bank client that has the right to access
and use the App for its own use. Under this license, the End User may only be
You or an employee in the organization to which You belong.

1.6. "Market Open Hours" will mean the period during which trading occurs on
one of the markets supported by the Trading Platform.

1.7. "Open API" will mean as set forth in the recitals to this License the
data and functionality (commonly referred to as the application programming
interface or API) documented on Saxo Bank's developer portal, a system
developed by Saxo Bank and updated from time to time for providing third party
applications programmatic access to certain parts of Saxo Bank's trading
infrastructure.

1.8. "Party" will mean You or Saxo Bank, as applicable, and "Parties" will
mean You and Saxo Bank.

1.9. "Refresh Token" will mean a token which the App may use together with the
App Key and App Secret to obtain a new Access Token.

1.10. "Saxo Authentication System" will mean the system which provides Access
Tokens and (possibly) Refresh Tokens to the App in response to successful End
User and App authentication.

1.11. "Services" will mean Your services via the App.

1.12. "Service Window" will mean a period outside of Market Open Hours, during
which period Saxo Bank may upgrade the Trading Platform and where the Trading
Platform and Open API may be unavailable or partially unavailable.

1.13. "Trademarks" will mean all proprietary indicia, trademarks, tradenames,
symbols, logos and/or brand names adopted from time to time to identify You or
Saxo Bank, as applicable, or any of its products or services.

1.14. "Transaction" will mean a transaction involving the sale or purchase of
certain Agreed Financial Instruments listed on a [continues]

### 2. RIGHTS GRANTED AND SERVICES

2.1. Subject to the terms and conditions in this License Saxo Bank grants You
the personal non-transferal right to use Your own internal proprietary software
tools to connect to Open API for the purpose of managing and trading on Your
accounts held with Saxo Bank.

2.2. Subject to the terms and conditions of this License, You hereby grant
Saxo Bank the right to mention or promote Your App on Saxo Bank's websites.

### 3. INTELLECTUAL PROPERTY RIGHTS

3.1. Saxo Bank will retain all intellectual property rights relating to Saxo
Bank's Trading Platforms, including all improvements, modifications,
translations and derivative works thereof ("Saxo Bank IP").

3.2. Neither Party will use the other Party's intellectual property rights
other than in accordance with this License and in compliance with all
applicable laws and regulations.

### 4. LIMITATION OF LIABILITY

4.1. You acknowledge and accept that End User uses the App and Open API at its
own risk and Saxo Bank is not liable for any use of the App or any of the
Services provided via the App to End Users. All conditions, warranties,
covenants, representations and undertakings which might be implied, whether
statutory or otherwise, in respect of Saxo Bank's obligations hereunder are
excluded to the maximum extent permitted by law. You acknowledge and accept
that any information received through Open API may be inaccurate, incomplete
and/or not up to date.

4.2. Saxo Bank shall not have any relationship with End User in connection with
their use of the App and You are fully responsible for ensuring that the use of
the App by End Users from any location:
a) is fully in accordance with all applicable local laws and regulations.
b) is not in any way unlawful or fraudulent or has any unlawful or fraudulent
purpose or effect.
c) is not knowingly or intentionally transmitting or introducing any viruses,
trojans, worms, logic-bombs, keystroke loggers, spyware, adware, denial of
service attacks or any other harmful programs, or similar computer code which
is malicious or technologically harmful and is designed to damage or adversely
affect the content, software or performance of the Open API or the operation of
any other computer software or hardware.

4.3. In the event that Saxo Bank is liable to You, Saxo Bank's total liability
to You in respect of all claims arising out of or in connection with this
License shall be limited to EUR 20,000.00 in any twelve-month period.

### 5. INDEMNIFICATION

5.1. You will defend at Your expense any third party claim, suit or proceeding
by any third party (each, a "Claim") brought against Saxo Bank (a) that arises
from a breach by You of any representation or warranty in this License or (b)
that Your Service or Software infringes such third party's intellectual property
rights, and You will pay all costs and damages finally awarded against Saxo Bank
by a court of competent jurisdiction as a result of any such claim or required
to be paid by Saxo Bank pursuant to a settlement License to which You agree in
writing in settlement of such a Claim.

### 6. TERMINATION

6.1. This License and the rights granted hereunder will terminate
automatically: (a) if You fail to comply with any term(s) of this License and
fail to cure such breach within 14 days of becoming aware of such breach; (b)
if You are no longer a client of Saxo Bank; or (c) if You, at any time during
the term of this License, commence an action for patent infringement against
Saxo Bank.

6.2. Saxo Bank may in addition terminate this License immediately for
convenience at any time by giving You a written notification, if in Saxo Bank's
reasonable opinion such termination is deemed necessary.

### 7. SPECIAL MARKET CONDITIONS

7.1. Saxo Bank is entitled, in its reasonable professional opinion, to
determine that an emergency or exceptional market condition exists. Such
conditions include the suspension or closure of any market, the abandonment or
failure of any event to which Saxo Bank relates its quotes or the occurrence of
an excessive movement in the level of any trade and/or underlying market or
Saxo Bank's reasonable anticipation of the occurrence of such a movement. In
such cases, Saxo Bank shall also be entitled to close or limit the access to
Your App immediately without notice to You.

### 8. TECHNICAL REQUIREMENTS TO APP AND YOU

8.1. To identify the App platform Saxo Bank will issue to You a set of App
Keys and App Secrets. These are strictly confidential and non-transferrable.

8.2. The authentication of an End User must be done by the End User entering
credentials into a login dialog provided by the Saxo Bank Login System. Under
no circumstances is the App allowed to intercept the traffic between the
browser and the Saxo Bank Login System, nor is the App allowed to present a
login dialog to the End User and forward the information entered by the End
User to the Saxo Login System.

8.3. During the authentication process the App will receive an "Access Token"
and possibly a "Refresh Token" unique to each authenticated End User. The App
must only use the Refresh Token in direct communication with the Saxo
Authentication Server for the purpose of obtaining a new Access Token.

8.4. It is the App's sole responsibility to monitor and restrict the access and
usage of the Open API via the App.

8.5. Notwithstanding anything to the contrary in this License, You shall be
fully responsible for any Transactions effected in the Open API via the App.

8.6. The App is also responsible for the correct display of any information
conveyed to the End User including information about any End User positions,
orders, holdings, margin status, trade confirmations, and quotes as well as any
other information the App may have received from the Open API.

8.7. In case the App is used by more than one End User You are solely
responsible for ensuring that no Transaction and no End User Information
pertaining to one End User is effected on behalf of or displayed to another
End User.

8.8. You will undertake best efforts to ensure that it complies at all times
with all applicable laws, rules and regulations, (including those of any
exchange), the terms and conditions of this License, any and all disclaimers
and additional terms and conditions presented in any part of the Open API and
any other terms and conditions pertaining to it as from time to time in effect.
Furthermore, You are under an obligation to provide Saxo Bank with such
information as it may request from time to time in order to comply with Saxo
Bank's obligations with the exchanges.

8.9. For any sustained damages, which Saxo Bank suffers from Your failure to
take adequate steps to protect the security of any such credentials, and
prevent any person from any unauthorized use, or Your failure to comply with
all applicable laws, rules and regulations (including those of any exchange)
arising from this License, and any additional terms and conditions, You shall
hold Saxo Bank harmless in any legal, administrative or arbitral proceedings
and expenses related thereto, and shall indemnify Saxo Bank for all damages,
costs and expenses arising as a result of non-compliance with this section or
any other section in this License.

### 9. OPEN API ENVIRONMENTS

9.1. Open API is available in two different environments.

9.2. The Simulation environment also known as the "Demo environment" is a copy
of the live environment, and most functionality on the live environment is also
available on the simulation environment.

9.3. You are expected to verify your software against the simulation
environment before proceeding to access the live environment. You are also
expected to continue to run services against the simulation environment as a
way to spot potential issues due to changes in the API as soon as possible.

9.4. Both the simulation environment and the live environment are subject to
the Saxo Bank's standard hours of operation and Service Window; however
incidents on the simulation system are treated with lower priority than
incidents on the live [continues]

### 10. VERIFICATION

10.1. You acknowledge and agree that You shall be solely responsible for
verifying the compatibility of the Open API with Your App and for reviewing any
proposed modifications to the App and the Open API. The Open API may be
verified via Saxo Bank's Simulation environment ("Demo environment"). Saxo Bank
retains the right to require You to demonstrate to Saxo Bank the functionality
of your App as it pertains to integrating with the Open API and to verify such
functionality adheres to the Open API.

10.2. You acknowledge and agree that You shall be solely responsible for
testing the End User's access to the App and the End User's ability to operate
the App correctly.

### 11. MODIFICATIONS TO THE SERVICE

11.1. You acknowledge and agree that the Open API may be modified, suspended or
withdrawn by Saxo Bank at its sole discretion. Saxo Bank will make regular
modifications to the Open API, having no effect on the End User's features with
no prior notice. Should Saxo Bank need to introduce new features which are not
backwardly compatible with the old features, Saxo Bank will attempt to inform
You at least thirty (30) days prior to any such modification of the Open API.
Saxo Bank may inform You directly or simply through the posting of release notes
on our website. You are required to update your App so as to be able to function
properly with the modified Open API. You are obliged to inform and notify any
End User of such modification, suspension or withdrawal which may affect any End
User's access to and use of the Open API via the App.

11.2. Notwithstanding anything to the contrary herein, Saxo Bank shall be
entitled to modify, suspend or withdraw/disconnect the Open API at any time to
the extent that Saxo Bank determines that such modification, suspension or
withdrawal/disconnection is necessary to avoid material errors or Unauthorized
Activity from occurring no matter whether such material error or Unauthorized
Activity is caused by You or any End User. You shall be informed as soon as
possible to such modification or suspension. You are obliged to inform and
notify any End Users of such modification, suspension or withdrawal/disconnect
which may affect any End User's access to and use of the Open API via the App.

### 12. PUBLIC ANNOUNCEMENT

12.1. You will not make any separate public announcement regarding this License
or any of the contents contained herein without the prior written consent of
Saxo Bank.

### 13. SEVERABILITY

13.1. The terms and conditions of this License are severable. If any term or
condition of this License is deemed to be illegal or unenforceable under any
rule of law, all other terms shall remain in force. Further, the term or
condition which is held to be illegal or unenforceable shall remain in effect
as far as possible in accordance with the intention of the Parties as of the
Effective Date.

### 14. RELATIONSHIP OF THE PARTIES

14.1. Nothing in this License shall be construed to place the Parties hereto in
an agency, employment, franchise, joint venture, or partnership relationship.
Neither Party will have the authority to obligate or bind the other in any
manner, and nothing herein contained shall give rise or is intended to give rise
to any rights of any kind to any third parties. Neither Party will represent to
the contrary, either expressly, implicitly or otherwise.

### 15. GOVERNING LAW AND CHOICE OF JURISDICTION

15.1. This License is subject to the laws of Denmark and both parties hereby
irrevocably submit to the exclusive jurisdiction of the Danish Courts. This
License contains the entire License between the parties with respect to the
subject matter hereof and supersedes all previous conditions, understandings,
commitments, Licenses, or representations whatsoever, whether oral or written,
relating to the subject matter hereof. Any failure to enforce any provision of
this License shall not constitute a waiver thereof or of any other provision.
This License may not be amended, nor any obligation waived, except in writing
and signed by all the parties hereto.

### 16. ACCEPTANCE OF THE LICENSE

16.1. By signing and returning this document You acknowledge that You are
legally bound by this License. If You are entering into this License on behalf
of Your employer or other entity, You represent and warrant that You have full
legal authority to bind your employer or such entity to this License.
