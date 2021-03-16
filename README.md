# Hyperledger Aries Cloud Agent - Python

> Forked from the main Hyperledger ACA to add Verses specific setup parameters, specifically with the Flying Forward 2020 project

## Overview

Hyperledger Aries Cloud Agent Python (ACA-Py) is a foundation for building Verifiable Credential (VC) ecosystems. It operates in the second and third layers of the [Trust Over IP framework (PDF)](https://trustoverip.org/wp-content/uploads/sites/98/2020/05/toip_050520_primer.pdf) using [DIDComm messaging](https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0005-didcomm) and [Hyperledger Aries](https://www.hyperledger.org/use/aries) protocols. The "cloud" in the name means that ACA-Py runs on servers (cloud, enterprise, IoT devices, and so forth), but is not designed to run on mobile devices.

ACA-Py is built on the Aries concepts and features that make up [Aries Interop Profile (AIP) 1.0](https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0302-aries-interop-profile), as well as many of the protocols that will be in [AIP 2.0](https://github.com/hyperledger/aries-rfcs/pull/579). [ACA-Py’s supported Aries protocols](https://github.com/hyperledger/aries-cloudagent-python/blob/main/SupportedRFCs.md) include, most importantly, protocols for issuing, verifying, and holding VCs that work with a [Hyperledger Indy](https://github.com/hyperledger/indy-sdk) distributed ledger and the Indy "AnonCreds" credential format. Contributors are actively working on adding support for other ToIP Layer 1 DID Utilities, and for other VC formats.

To use ACA-Py you create a business logic controller that "talks to" ACA-Py (sending HTTP requests and receiving webhook notifications), and ACA-Py handles the rest. That controller can be built in any language that supports making and receiving HTTP requests; knowledge of Python is not needed. Together, this means you can focus on building VC solutions using familiar web development technologies, instead of having to learn the nuts and bolts of low-level cryptography and Trust over IP-type protocols.

ACA-Py supports "multi-tenant" scenarios. In these scenarios, one (scalable) instance of ACA-Py uses one database instance, and are together capable of managing separate secure storage (for private keys, DIDs, credentials, etc.) for many different actors. This enables (for example) an "issuer-as-a-service", where an enterprise may have many VC issuers, each with different identifiers, using the same instance of ACA-Py to interact with VC holders as required. Likewise, an ACA-Py instance could be a "cloud wallet" for many holders (e.g. people or organizations) that, for whatever reason, cannot use a mobile device for a wallet. Learn more about multi-tenant deployments [here](./Multitenancy.md).

Startup options allow the use of an ACA-Py as an Aries [mediator](https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0046-mediators-and-relays#summary) using core Aries protocols to coordinate its mediation role. Such an ACA-Py instance receives, stores and forwards messages to Aries  agents that (for example) lack an addressable endpoint on the Internet such as a mobile wallet. A live instance of a public mediator based on ACA-Py is available [here](https://indicio-tech.github.io/mediator/) from Indicio Technologies. Learn more about deploying a mediator [here](./Mediation.md).

ACA-Py supports deployments in scaled environments such as in Kubernetes environments where ACA-Py and its storage components can be horizontally scaled as needed to handle the load.

## Setup

All of the necessary parameters are stored in a YAML found in the Docker folder. To create and run the agent in a Docker container, ```cd``` into the root folder and run:
```
PORTS="8020:8020 8021:8021" ./scripts/run_docker start --arg-file ./verses_config.yaml
```

If everything has worked you will receive a startup message in the terminal that looks like:
```
::::::::::::::::::::::::::::::::::::::::::::::
:: VersesBaseAgent                          ::
::                                          ::
::                                          ::
:: Inbound Transports:                      ::
::                                          ::
::   - http://0.0.0.0:8020                  ::
::                                          ::
:: Outbound Transports:                     ::
::                                          ::
::   - http                                 ::
::   - https                                ::
::                                          ::
:: Public DID Information:                  ::
::                                          ::
::   - DID: XwEvTG8zcnZv2ZoE2MHKDa          ::
::                                          ::
:: Administration API:                      ::
::                                          ::
::   - http://0.0.0.0:8021                  ::
::                                          ::
::                               ver: 0.6.0 ::
::::::::::::::::::::::::::::::::::::::::::::::

Listening...

```
You can then go to the Admin API at localhost:8021 to interact with it directly, but the FF2020 API is already configured to perform and parse all the necessary functions
