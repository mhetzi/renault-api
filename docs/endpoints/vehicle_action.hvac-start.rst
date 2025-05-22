actions/hvac-start
''''''''''''''''''

.. rst-class:: endpoint

Base url:
   ``/commerce/v1/accounts/{account_id}/kamereon/kca/car-adapter/v1/cars/{vin}/actions/hvac-start``

Sample payload:
   Start HVAC:

   .. code-block:: JavaScript

      {
         "data": {
            "type": "HvacStart",
            "attributes": {
               "action": "start"
            }
         }
      }

   Stop HVAC:

   .. code-block:: JavaScript

      {
         "data": {
            "type": "HvacStart",
            "attributes": {
               "action": "stop"
            }
         }
      }

.. note::
   On Zoe50 (model code X102VE):
      Payload ``{'action': 'cancel'}`` to stop HVAC does not create errors but has no effect on the vehicle (Renault side limitation).
